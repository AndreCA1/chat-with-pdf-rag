from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langchain_core.documents import Document as TextChunk

from app.config import EMBEDDING_MODEL, RETRIEVER_TOP_K
from app.database import SessionLocal
from app.models import Document
from app.rag.vectorstore import (
    DocumentRetriever,
    build_chunks,
    build_retriever,
    get_embeddings,  # a versão real: o fixture só substitui o nome dentro do módulo
)


@pytest.fixture
def make_document(user):
    def _make_document(*texts: str) -> UUID:
        splits = [
            TextChunk(page_content=text, metadata={"page": page})
            for page, text in enumerate(texts)
        ]
        document = Document(owner_id=user.id, filename="d.pdf", chunk_count=len(texts))
        chunks = build_chunks(splits)
        with SessionLocal() as session:
            session.add(document)
            session.flush()
            for chunk in chunks:
                chunk.document_id = document.id
            session.add_all(chunks)
            session.commit()
        return document.id

    return _make_document


def retriever_for(document_id: UUID, **kwargs) -> DocumentRetriever:
    return DocumentRetriever(
        document_id=document_id, session_factory=SessionLocal, **kwargs
    )


def test_get_embeddings_loads_the_model_only_once(monkeypatch):
    model_class = MagicMock()
    monkeypatch.setattr("app.rag.vectorstore.HuggingFaceEmbeddings", model_class)
    get_embeddings.cache_clear()
    try:
        assert get_embeddings() is get_embeddings()
    finally:
        get_embeddings.cache_clear()

    model_class.assert_called_once_with(model_name=EMBEDDING_MODEL)


def test_build_chunks_converts_each_split(fake_embeddings):
    splits = [
        TextChunk(page_content="gatos", metadata={"page": 3}),
        TextChunk(page_content="cachorros"),
    ]

    chunks = build_chunks(splits)

    assert [chunk.content for chunk in chunks] == ["gatos", "cachorros"]
    assert [chunk.page for chunk in chunks] == [3, None]
    assert chunks[0].embedding == fake_embeddings.embed_query("gatos")


def test_retriever_returns_the_closest_chunk_first(make_document):
    document_id = make_document(
        "fala sobre gatos", "fala sobre cachorros", "fala sobre peixes"
    )

    results = retriever_for(document_id).invoke("cachorros")

    assert results[0].page_content == "fala sobre cachorros"
    assert results[0].metadata == {"page": 1}


def test_retriever_only_searches_the_given_document(make_document):
    first = make_document("assunto de gatos")
    second = make_document("gatos gatos gatos")

    results = retriever_for(first).invoke("gatos")

    assert [result.page_content for result in results] == ["assunto de gatos"]
    assert second != first


def test_retriever_uses_the_default_limit(make_document):
    document_id = make_document(*[f"texto {i}" for i in range(RETRIEVER_TOP_K + 3)])
    assert len(retriever_for(document_id).invoke("texto")) == RETRIEVER_TOP_K


def test_retriever_accepts_a_custom_limit(make_document):
    document_id = make_document("um", "dois", "tres")
    assert len(retriever_for(document_id, k=1).invoke("um")) == 1


def test_retriever_without_chunks_returns_an_empty_list(make_document):
    assert retriever_for(make_document()).invoke("gatos") == []


def test_in_memory_retriever_finds_the_closest_chunk():
    retriever = build_retriever(
        [TextChunk(page_content="gatos"), TextChunk(page_content="cachorros")]
    )
    assert retriever.invoke("cachorros")[0].page_content == "cachorros"


def test_in_memory_retriever_uses_the_default_limit():
    splits = [TextChunk(page_content=f"texto {i}") for i in range(RETRIEVER_TOP_K + 3)]
    assert len(build_retriever(splits).invoke("texto")) == RETRIEVER_TOP_K
