import logging
import tempfile

from fastapi import HTTPException, UploadFile, status

from app.config import MAX_UPLOAD_SIZE_MB
from app.rag.loader import load_and_split
from app.schemas import Source

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_FILENAME_LENGTH = 255
PDF_SIGNATURE = b"%PDF-"
EXCERPT_LENGTH = 200


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
