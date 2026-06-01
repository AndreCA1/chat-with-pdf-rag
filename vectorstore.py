# =============================================================================
# vectorstore.py — Banco vetorial (Chroma) e Retriever
# =============================================================================
# Responsabilidade única: transformar os chunks em embeddings e disponibilizar
# um Retriever — a ferramenta de busca semântica que a cadeia RAG vai usar.
#
# Diferença em relação à versão OpenAI:
#   Os embeddings agora são gerados localmente via sentence-transformers,
#   sem custo de API e com suporte nativo ao português.

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from config import EMBEDDING_MODEL


def build_retriever(splits: list) -> object:
    """
    Indexa os chunks num banco Chroma em memória e devolve um Retriever.

    Como funciona
    -------------
    1. Cada chunk é convertido em um vetor numérico (embedding) por um modelo
       local do HuggingFace — roda na sua máquina, sem custo de API.
    2. O Chroma armazena esses vetores em memória.
    3. O Retriever, ao receber uma pergunta, a transforma no mesmo espaço
       vetorial e devolve os N chunks mais próximos (mais relevantes).

    Parâmetros
    ----------
    splits : list[Document]
        Chunks gerados pelo módulo `loader`.

    Retorna
    -------
    VectorStoreRetriever
        Objeto pronto para ser plugado na cadeia RAG.
    """

    # Carrega o modelo de embeddings localmente.
    # Na primeira execução, o modelo (~90 MB) é baixado automaticamente
    # do HuggingFace Hub e cacheado para as próximas execuções.
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    # Cria o banco vetorial indexando todos os chunks de uma vez
    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
    )

    # Converte o banco em Retriever com comportamento de busca por similaridade
    retriever = vectorstore.as_retriever()

    print("[vectorstore] Banco vetorial criado e Retriever configurado.")
    return retriever