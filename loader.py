# =============================================================================
# loader.py — Carregamento e divisão de documentos
# =============================================================================
# Responsabilidade única: ler o arquivo de texto e transformá-lo em chunks
# prontos para serem indexados no banco vetorial.

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP, CHUNK_SIZE, DOCUMENT_PATH


def load_and_split(
    path: str = DOCUMENT_PATH,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list:
    """
    Carrega um arquivo .txt e o divide em chunks menores.

    Parâmetros
    ----------
    path : str
        Caminho para o arquivo de texto a ser processado.
    chunk_size : int
        Número máximo de caracteres por chunk.
    chunk_overlap : int
        Quantidade de caracteres compartilhados entre chunks adjacentes,
        evitando que informações importantes fiquem cortadas na fronteira.

    Retorna
    -------
    list[Document]
        Lista de objetos Document do LangChain, cada um representando um chunk.
    """

    loader = PyPDFLoader(path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    splits = splitter.split_documents(docs)

    print(f"[loader] {len(splits)} chunks gerados a partir de '{path}'.")
    return splits