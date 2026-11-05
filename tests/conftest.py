import hashlib
import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import make_url

# O app lê o ambiente ao ser importado, então as variáveis precisam ser definidas
# antes dos imports dele. Sem isso, os testes usariam o banco de desenvolvimento.
load_dotenv()
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or (
    make_url(os.environ["DATABASE_URL"])
    .set(database="rag_test")
    .render_as_string(hide_password=False)
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError("O banco de testes precisa ter um nome terminado em _test.")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET_KEY"] = "chave-usada-apenas-nos-testes-0123456789"
os.environ["OPENROUTER_API_KEY"] = "chave-falsa"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.embeddings import Embeddings  # noqa: E402
from langchain_core.language_models.fake_chat_models import (  # noqa: E402
    FakeListChatModel,
)
from pydantic import Field  # noqa: E402

from app.config import EMBEDDING_DIMENSIONS  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PASSWORD = "senha-segura-123"


class FakeEmbeddings(Embeddings):
    """Embeddings determinísticos: textos com as mesmas palavras ficam próximos."""

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        vector[0] = 0.01  # o pgvector não calcula a distância de um vetor zerado
        for word in re.findall(r"\w+", text.lower()):
            digest = hashlib.sha256(word.encode()).hexdigest()
            vector[int(digest, 16) % EMBEDDING_DIMENSIONS] += 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


class FakeLLM(FakeListChatModel):
    """Modelo de chat que guarda as mensagens recebidas e pode simular uma falha."""

    received: list = Field(default_factory=list)
    error: Any = None

    def _call(self, messages, *args, **kwargs):
        self.received.append(messages)
        if self.error is not None:
            raise self.error
        return super()._call(messages, *args, **kwargs)


def build_pdf(*pages: str) -> bytes:
    """Monta um PDF válido com uma página para cada texto (apenas ASCII)."""
    first_page_object = 4
    kids = " ".join(f"{first_page_object + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, page_text in enumerate(pages):
        escaped = (
            page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                "/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {first_page_object + 2 * index + 1} 0 R >>"
            ).encode()
        )
        objects.append(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (number, body)

    xref_offset = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        pdf += b"%010d 00000 n \n" % offset
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    pdf += b"startxref\n%d\n%%%%EOF\n" % xref_offset
    return bytes(pdf)


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    # Sem o alembic.ini, para o fileConfig do env.py não desligar os loggers do app.
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return config


@pytest.fixture(scope="session", autouse=True)
def database_schema(alembic_config):
    """Recria o banco de testes usando as migrations, como em produção."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    # As rotas abrem as próprias sessões e fazem commit, então não dá para isolar
    # os testes com rollback.
    yield
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users, login_attempts CASCADE"))


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch) -> FakeEmbeddings:
    embeddings = FakeEmbeddings()
    monkeypatch.setattr("app.rag.vectorstore.get_embeddings", lambda: embeddings)
    return embeddings


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch) -> FakeLLM:
    """Impede chamadas ao OpenRouter em qualquer teste."""
    llm = FakeLLM(responses=["Resposta de teste."])
    monkeypatch.setattr("app.rag.chain.ChatOpenAI", MagicMock(return_value=llm))
    return llm


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_user():
    def _make_user(email: str = "ana@exemplo.com", password: str = DEFAULT_PASSWORD):
        user = User(email=email, password_hash=hash_password(password))
        with SessionLocal() as session:
            session.add(user)
            session.commit()
        return user

    return _make_user


@pytest.fixture
def user(make_user) -> User:
    return make_user()


@pytest.fixture
def headers_for():
    def _headers_for(owner: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(owner.id)}"}

    return _headers_for


@pytest.fixture
def auth_headers(user, headers_for) -> dict[str, str]:
    return headers_for(user)


@pytest.fixture
def other_headers(make_user, headers_for) -> dict[str, str]:
    return headers_for(make_user("bruno@exemplo.com"))


@pytest.fixture
def upload(client):
    """Envia um PDF pela API e devolve a resposta."""

    def _upload(headers, *pages, filename="teste.pdf"):
        content = build_pdf(*pages) if pages else build_pdf("Texto padrao do documento")
        return client.post(
            "/documents",
            headers=headers,
            files={"file": (filename, content, "application/pdf")},
        )

    return _upload
