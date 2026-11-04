# =============================================================================
# api.py — API HTTP do sistema RAG
# =============================================================================
# Responsabilidade única: expor o fluxo RAG via HTTP. O processamento continua
# nos módulos `loader`, `vectorstore`, `chain` e `security`.
#
# Execução:      uvicorn api:app --reload
# Documentação:  http://127.0.0.1:8000/docs
#
# Os endpoints são funções síncronas de propósito: gerar embeddings e chamar o
# LLM são operações bloqueantes, e o FastAPI executa funções síncronas em um
# pool de threads, sem travar o servidor.
#
# As sessões do banco ficam abertas só durante as consultas. Assim, nenhuma
# conexão fica presa enquanto os embeddings são gerados ou o LLM responde.

import logging
import math
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from chain import build_rag_chain
from config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    MAX_PASSWORD_LENGTH,
    MAX_QUESTION_LENGTH,
    MAX_UPLOAD_SIZE_MB,
    MIN_PASSWORD_LENGTH,
    OPENROUTER_API_KEY,
)
from database import SessionLocal
from loader import load_and_split
from login_limiter import clear_login_attempts, reserve_login_attempt
from models import Document, User
from security import (
    create_access_token,
    hash_password,
    read_access_token,
    verify_password,
)
from vectorstore import DocumentRetriever, build_chunks

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_FILENAME_LENGTH = 255
PDF_SIGNATURE = b"%PDF-"
EXCERPT_LENGTH = 200
STATIC_DIR = Path(__file__).parent / "static"

# A interface só carrega arquivos próprios, o que limita o impacto de um XSS.
INTERFACE_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

app = FastAPI(
    title="Chat with PDF RAG",
    description="Crie uma conta, envie PDFs e faça perguntas sobre o conteúdo deles.",
    version="2.1.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# auto_error=False para que um token ausente receba a mesma resposta que um
# token inválido.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterRequest(BaseModel):
    email: Annotated[EmailStr, AfterValidator(normalize_email)]
    password: Annotated[
        str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    ]


class UserResponse(BaseModel):
    id: UUID
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DocumentResponse(BaseModel):
    id: UUID
    filename: str | None
    chunks: int
    created_at: datetime


class QuestionRequest(BaseModel):
    question: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH
        ),
    ]


class Source(BaseModel):
    page: int | None
    excerpt: str


class AnswerResponse(BaseModel):
    answer: str
    sources: list[Source]


def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> User:
    """Identifica o usuário pelo token, com a mesma resposta para qualquer falha."""
    user_id = read_access_token(token) if token else None
    user = None
    if user_id is not None:
        with SessionLocal() as session:
            user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token de acesso ausente, inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def read_pdf(file: UploadFile) -> bytes:
    """Lê o arquivo respeitando o limite de tamanho e confere se é um PDF."""
    content = file.file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"O arquivo excede o limite de {MAX_UPLOAD_SIZE_MB} MB.",
        )
    # A assinatura é verificada porque o Content-Type é informado pelo cliente.
    if not content.startswith(PDF_SIGNATURE):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "O arquivo enviado não é um PDF.",
        )
    return content


def split_pdf(content: bytes) -> list:
    """Divide o PDF em chunks usando um arquivo temporário, removido ao final."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
        temp_file.write(content)
        temp_file.flush()
        try:
            splits = load_and_split(temp_file.name)
        except Exception as exc:
            # O pypdf não tem uma exceção única: PDFs corrompidos e protegidos
            # por senha geram tipos diferentes.
            logger.warning("Falha ao ler o PDF: %s", exc)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Não foi possível ler o PDF. Ele pode estar corrompido ou protegido por senha.",
            ) from exc

    # O PostgreSQL não aceita o caractere nulo em textos, e alguns PDFs o contêm.
    for split in splits:
        split.page_content = split.page_content.replace("\x00", "")

    # PDFs digitalizados (só imagem) não têm texto a ser extraído.
    splits = [split for split in splits if split.page_content.strip()]
    if not splits:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "O PDF não contém texto extraível.",
        )
    return splits


def clean_filename(filename: str | None) -> str | None:
    if filename is None:
        return None
    return filename.replace("\x00", "")[:MAX_FILENAME_LENGTH]


def to_document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        chunks=document.chunk_count,
        created_at=document.created_at,
    )


def build_sources(context: list) -> list[Source]:
    """Converte os chunks usados na resposta, com páginas numeradas a partir de 1."""
    sources = []
    for chunk in context:
        page = chunk.metadata.get("page")
        sources.append(
            Source(
                page=page + 1 if page is not None else None,
                excerpt=chunk.page_content[:EXCERPT_LENGTH],
            )
        )
    return sources


@app.get("/", include_in_schema=False)
def interface():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Content-Security-Policy": INTERFACE_CSP},
    )


@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma conta",
    tags=["Autenticação"],
    responses={409: {"description": "E-mail já cadastrado"}},
)
def register(body: RegisterRequest):
    user = User(email=body.email, password_hash=hash_password(body.password))
    with SessionLocal() as session:
        session.add(user)
        try:
            session.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "E-mail já cadastrado."
            ) from exc
    return UserResponse(id=user.id, email=user.email)


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Entra na conta e devolve um token de acesso",
    description="Informe o e-mail no campo `username`, como define o padrão OAuth2.",
    tags=["Autenticação"],
    responses={
        401: {"description": "E-mail ou senha incorretos"},
        429: {"description": "Limite de tentativas de login atingido"},
    },
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], response: Response):
    email = normalize_email(form.username)

    retry_after = reserve_login_attempt(email)
    if retry_after is not None:
        minutes = math.ceil(retry_after / 60)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Muitas tentativas de login. Tente novamente em {minutes} min.",
            headers={"Retry-After": str(retry_after)},
        )

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))

    # A senha é sempre verificada, para que o tempo de resposta não revele se o
    # e-mail existe. Senhas acima do limite nunca foram cadastradas.
    password_ok = verify_password(
        form.password[:MAX_PASSWORD_LENGTH + 1], user.password_hash if user else None
    )
    if not password_ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clear_login_attempts(email)

    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@app.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Envia e indexa um PDF",
    tags=["Documentos"],
    responses={
        401: {"description": "Token de acesso ausente, inválido ou expirado"},
        413: {"description": "Arquivo acima do limite de tamanho"},
        415: {"description": "O arquivo não é um PDF"},
        422: {"description": "PDF ilegível ou sem texto extraível"},
    },
)
def upload_document(
    file: Annotated[UploadFile, File(description="Arquivo PDF")],
    user: CurrentUser,
):
    splits = split_pdf(read_pdf(file))
    chunks = build_chunks(splits)

    document = Document(
        owner_id=user.id,
        filename=clean_filename(file.filename),
        chunk_count=len(chunks),
    )
    with SessionLocal() as session:
        session.add(document)
        session.flush()
        for chunk in chunks:
            chunk.document_id = document.id
        session.add_all(chunks)
        session.commit()
    return to_document_response(document)


@app.get(
    "/documents",
    response_model=list[DocumentResponse],
    summary="Lista os documentos do usuário",
    tags=["Documentos"],
    responses={401: {"description": "Token de acesso ausente, inválido ou expirado"}},
)
def list_documents(user: CurrentUser):
    with SessionLocal() as session:
        documents = session.scalars(
            select(Document)
            .where(Document.owner_id == user.id)
            .order_by(Document.created_at.desc())
        ).all()
    return [to_document_response(document) for document in documents]


@app.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um documento do usuário e seus trechos indexados",
    tags=["Documentos"],
    responses={
        401: {"description": "Token de acesso ausente, inválido ou expirado"},
        404: {"description": "Documento não encontrado"},
    },
)
def delete_document(document_id: UUID, user: CurrentUser):
    # Os trechos são removidos pelo ON DELETE CASCADE da chave estrangeira.
    with SessionLocal() as session:
        result = session.execute(
            delete(Document).where(
                Document.id == document_id,
                Document.owner_id == user.id,
            )
        )
        session.commit()
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")


@app.post(
    "/documents/{document_id}/questions",
    response_model=AnswerResponse,
    summary="Faz uma pergunta sobre um documento do usuário",
    tags=["Documentos"],
    responses={
        401: {"description": "Token de acesso ausente, inválido ou expirado"},
        404: {"description": "Documento não encontrado"},
        502: {"description": "Falha ao consultar o LLM"},
        503: {"description": "Chave do LLM não configurada"},
    },
)
def ask_question(document_id: UUID, body: QuestionRequest, user: CurrentUser):
    # O filtro por dono faz o documento de outra pessoa ter a mesma resposta de
    # um documento inexistente.
    with SessionLocal() as session:
        owned_document_id = session.scalar(
            select(Document.id).where(
                Document.id == document_id,
                Document.owner_id == user.id,
            )
        )
    if owned_document_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")

    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "OPENROUTER_API_KEY não configurada no servidor.",
        )

    retriever = DocumentRetriever(
        document_id=owned_document_id,
        session_factory=SessionLocal,
    )
    try:
        result = build_rag_chain(retriever).invoke({"input": body.question})
    except Exception as exc:
        # O detalhe fica no log para não expor dados internos ao cliente.
        logger.exception("Falha ao gerar a resposta")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Não foi possível gerar a resposta. Tente novamente.",
        ) from exc

    return AnswerResponse(
        answer=result["answer"],
        sources=build_sources(result["context"]),
    )
