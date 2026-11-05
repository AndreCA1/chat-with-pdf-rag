from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.config import MAX_QUESTION_LENGTH, RETRIEVER_TOP_K
from app.database import SessionLocal
from app.models import Chunk, Document
from tests.conftest import build_pdf


def count_chunks(document_id: str) -> int:
    with SessionLocal() as session:
        return session.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.document_id == UUID(document_id))
        )


def post_file(client, headers, content, filename="teste.pdf"):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": (filename, content, "application/pdf")},
    )


def ask(client, headers, document_id, question="Qual o tema?"):
    return client.post(
        f"/documents/{document_id}/questions",
        headers=headers,
        json={"question": question},
    )


@pytest.fixture
def document(auth_headers, upload) -> dict:
    return upload(
        auth_headers,
        "Primeira pagina sobre gatos",
        "Segunda pagina sobre cachorros",
        filename="animais.pdf",
    ).json()


# Upload


def test_upload_indexes_the_pdf(user, auth_headers, upload):
    response = upload(auth_headers, "Pagina um", "Pagina dois", filename="doc.pdf")

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "doc.pdf"
    assert body["chunks"] == 2
    assert count_chunks(body["id"]) == 2
    with SessionLocal() as session:
        assert session.get(Document, UUID(body["id"])).owner_id == user.id


def test_upload_stores_the_content_and_embedding(auth_headers, upload, fake_embeddings):
    document_id = upload(auth_headers, "Texto sobre gatos").json()["id"]

    with SessionLocal() as session:
        chunk = session.scalar(
            select(Chunk).where(Chunk.document_id == UUID(document_id))
        )
    assert chunk.page == 0
    assert chunk.content == "Texto sobre gatos"
    assert list(chunk.embedding) == fake_embeddings.embed_query("Texto sobre gatos")


def test_upload_requires_authentication(client):
    response = post_file(client, {}, build_pdf("Texto"))
    assert response.status_code == 401


def test_upload_rejects_files_that_are_not_pdf(client, auth_headers):
    # O Content-Type diz que é PDF, mas o conteúdo não tem a assinatura.
    response = post_file(client, auth_headers, b"apenas um texto")
    assert response.status_code == 415


def test_upload_rejects_files_above_the_limit(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.services.documents.MAX_UPLOAD_SIZE_BYTES", 10)
    response = post_file(client, auth_headers, build_pdf("Texto"))
    assert response.status_code == 413


def test_upload_rejects_a_corrupted_pdf(client, auth_headers):
    response = post_file(client, auth_headers, b"%PDF-1.4 conteudo corrompido")

    assert response.status_code == 422
    assert "corrompido" in response.json()["detail"]


def test_upload_rejects_a_pdf_without_text(client, auth_headers):
    response = post_file(client, auth_headers, build_pdf(""))

    assert response.status_code == 422
    assert response.json()["detail"] == "O PDF não contém texto extraível."


def test_failed_upload_saves_nothing(client, auth_headers):
    post_file(client, auth_headers, build_pdf(""))

    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0


# Listagem


def test_list_requires_authentication(client):
    assert client.get("/documents").status_code == 401


def test_list_is_empty_for_a_new_user(client, auth_headers):
    response = client.get("/documents", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_shows_the_newest_first(client, auth_headers, upload):
    upload(auth_headers, filename="antigo.pdf")
    upload(auth_headers, filename="novo.pdf")

    documents = client.get("/documents", headers=auth_headers).json()

    assert [item["filename"] for item in documents] == ["novo.pdf", "antigo.pdf"]
    assert set(documents[0]) == {"id", "filename", "chunks", "created_at"}


def test_list_hides_documents_from_other_users(
    client, auth_headers, other_headers, document
):
    assert client.get("/documents", headers=other_headers).json() == []


# Exclusão


def test_delete_requires_authentication(client, document):
    assert client.delete(f"/documents/{document['id']}").status_code == 401


def test_delete_removes_the_document_and_its_chunks(client, auth_headers, document):
    response = client.delete(f"/documents/{document['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert client.get("/documents", headers=auth_headers).json() == []
    assert count_chunks(document["id"]) == 0


def test_delete_cannot_remove_a_document_from_another_user(
    client, auth_headers, other_headers, document
):
    response = client.delete(f"/documents/{document['id']}", headers=other_headers)

    assert response.status_code == 404
    assert len(client.get("/documents", headers=auth_headers).json()) == 1
    assert count_chunks(document["id"]) == document["chunks"]


def test_delete_of_an_unknown_document_returns_404(client, auth_headers):
    response = client.delete(f"/documents/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404


def test_delete_with_an_invalid_id_returns_422(client, auth_headers):
    response = client.delete("/documents/nao-e-uuid", headers=auth_headers)
    assert response.status_code == 422


# Perguntas


def test_question_requires_authentication(client, document):
    response = client.post(
        f"/documents/{document['id']}/questions", json={"question": "Qual o tema?"}
    )
    assert response.status_code == 401


def test_question_returns_the_answer_and_sources(client, auth_headers, document):
    response = ask(client, auth_headers, document["id"], "cachorros")

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Resposta de teste."
    # O trecho mais próximo vem primeiro, com a página numerada a partir de 1.
    assert body["sources"][0] == {
        "page": 2,
        "excerpt": "Segunda pagina sobre cachorros",
    }
    assert len(body["sources"]) == 2


def test_question_sends_the_context_and_question_to_the_llm(
    client, auth_headers, document, fake_llm
):
    ask(client, auth_headers, document["id"], "Fale sobre gatos")

    system_message, human_message = fake_llm.received[0]
    assert "Primeira pagina sobre gatos" in system_message.content
    assert human_message.content == "Fale sobre gatos"


def test_question_only_uses_chunks_from_the_requested_document(
    client, auth_headers, upload, document, fake_llm
):
    other = upload(auth_headers, "Conteudo secreto sobre gatos").json()

    response = ask(client, auth_headers, document["id"], "gatos")

    excerpts = [source["excerpt"] for source in response.json()["sources"]]
    assert "Conteudo secreto sobre gatos" not in excerpts
    assert "Conteudo secreto" not in fake_llm.received[0][0].content
    assert other["id"] != document["id"]


def test_question_limits_the_number_of_sources(client, auth_headers, upload):
    pages = [f"Pagina numero {i}" for i in range(RETRIEVER_TOP_K + 2)]
    document_id = upload(auth_headers, *pages).json()["id"]

    response = ask(client, auth_headers, document_id, "numero")

    assert len(response.json()["sources"]) == RETRIEVER_TOP_K


def test_question_about_a_document_from_another_user_returns_404(
    client, other_headers, document, fake_llm
):
    response = ask(client, other_headers, document["id"])

    assert response.status_code == 404
    assert fake_llm.received == []


def test_question_about_an_unknown_document_returns_404(client, auth_headers):
    assert ask(client, auth_headers, uuid4()).status_code == 404


@pytest.mark.parametrize(
    "question",
    [
        pytest.param("   ", id="em-branco"),
        pytest.param("a" * (MAX_QUESTION_LENGTH + 1), id="longa-demais"),
    ],
)
def test_question_is_validated(client, auth_headers, document, question):
    assert ask(client, auth_headers, document["id"], question).status_code == 422


def test_question_without_an_api_key_returns_503(
    client, auth_headers, document, monkeypatch
):
    monkeypatch.setattr("app.routers.documents.OPENROUTER_API_KEY", None)
    assert ask(client, auth_headers, document["id"]).status_code == 503


def test_llm_failure_returns_502_without_exposing_details(
    client, auth_headers, document, fake_llm
):
    fake_llm.error = RuntimeError("segredo interno do provedor")

    response = ask(client, auth_headers, document["id"])

    assert response.status_code == 502
    assert "segredo" not in response.text
