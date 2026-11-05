# =============================================================================
# vectorstore.py — Embeddings e Retrievers
# =============================================================================
# Responsabilidade única: transformar textos em embeddings e disponibilizar os
# Retrievers — a ferramenta de busca semântica que a cadeia RAG vai usar.
#
# A API guarda os vetores no PostgreSQL com pgvector. O modo de terminal
# (cli.py) usa um banco vetorial em memória e não depende do PostgreSQL.
#
# Diferença em relação à versão OpenAI:
#   Os embeddings agora são gerados localmente via sentence-transformers,
#   sem custo de API e com suporte nativo ao português.

from collections.abc import Callable
from functools import lru_cache
from uuid import UUID

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import EMBEDDING_MODEL, RETRIEVER_TOP_K
from app.models import Chunk


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Carrega o modelo uma única vez na primeira execução, e fica na cache, reaproveitando-o entre os documentos e para as próximas execuções.
    """
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def build_chunks(splits: list) -> list[Chunk]:
    """Gera os embeddings dos trechos e os converte em linhas da tabela `chunks`."""
    vectors = get_embeddings().embed_documents(
        [split.page_content for split in splits]
    )
    return [
        Chunk(
            page=split.metadata.get("page"),
            content=split.page_content,
            embedding=vector,
        )
        for split, vector in zip(splits, vectors)
    ]


class DocumentRetriever(BaseRetriever):
    """
    Busca os trechos mais próximos da pergunta dentro de um único documento.

    Recebe uma fábrica de sessões porque a cadeia RAG pode executá-lo em outra
    thread, e abre a conexão só durante a consulta.
    """

    document_id: UUID
    session_factory: Callable[[], Session]
    k: int = RETRIEVER_TOP_K

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        vector = get_embeddings().embed_query(query)
        statement = (
            select(Chunk)
            .where(Chunk.document_id == self.document_id)
            .order_by(Chunk.embedding.cosine_distance(vector))
            .limit(self.k)
        )
        with self.session_factory() as session:
            chunks = session.scalars(statement).all()
        return [
            Document(page_content=chunk.content, metadata={"page": chunk.page})
            for chunk in chunks
        ]


def build_retriever(splits: list) -> object:
    """
    Indexa os chunks em um banco vetorial em memória e devolve um Retriever.

    Usado pelo modo de terminal. Os dados são perdidos ao encerrar o programa.
    """
    vectorstore = InMemoryVectorStore.from_documents(
        documents=splits,
        embedding=get_embeddings(),
    )
    retriever = vectorstore.as_retriever(search_kwargs={"k": RETRIEVER_TOP_K})

    print("[vectorstore] Banco vetorial criado e Retriever configurado.")
    return retriever
