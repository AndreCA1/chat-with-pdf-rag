import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import delete, select

from app.config import OPENROUTER_API_KEY
from app.database import SessionLocal
from app.dependencies import CurrentUser
from app.models import Document
from app.rag.chain import build_rag_chain
from app.rag.vectorstore import DocumentRetriever, build_chunks
from app.schemas import AnswerResponse, DocumentResponse, QuestionRequest
from app.services.documents import (
    build_sources,
    clean_filename,
    read_pdf,
    split_pdf,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documentos"])


def to_document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        chunks=document.chunk_count,
        created_at=document.created_at,
    )


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Envia e indexa um PDF",
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


@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="Lista os documentos do usuário",
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


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui um documento do usuário e seus trechos indexados",
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


@router.post(
    "/{document_id}/questions",
    response_model=AnswerResponse,
    summary="Faz uma pergunta sobre um documento do usuário",
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
