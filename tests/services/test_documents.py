from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from langchain_core.documents import Document

from app.services.documents import (
    EXCERPT_LENGTH,
    MAX_FILENAME_LENGTH,
    build_sources,
    clean_filename,
    read_pdf,
    split_pdf,
)
from tests.conftest import build_pdf


def upload_file(content: bytes) -> UploadFile:
    return UploadFile(file=BytesIO(content), filename="teste.pdf")


def replace_loader(monkeypatch, splits: list[Document]) -> None:
    monkeypatch.setattr("app.services.documents.load_and_split", lambda _path: splits)


# read_pdf


def test_read_pdf_returns_the_content():
    content = build_pdf("Texto")
    assert read_pdf(upload_file(content)) == content


def test_read_pdf_accepts_a_file_at_the_limit(monkeypatch):
    monkeypatch.setattr("app.services.documents.MAX_UPLOAD_SIZE_BYTES", 10)
    assert read_pdf(upload_file(b"%PDF-12345")) == b"%PDF-12345"


def test_read_pdf_rejects_a_file_above_the_limit(monkeypatch):
    monkeypatch.setattr("app.services.documents.MAX_UPLOAD_SIZE_BYTES", 10)

    with pytest.raises(HTTPException) as error:
        read_pdf(upload_file(b"%PDF-123456"))

    assert error.value.status_code == 413


@pytest.mark.parametrize("content", [b"", b"texto", b" %PDF-1.4"])
def test_read_pdf_requires_the_signature_at_the_start(content):
    with pytest.raises(HTTPException) as error:
        read_pdf(upload_file(content))

    assert error.value.status_code == 415


# split_pdf


def test_split_pdf_reads_a_real_pdf():
    splits = split_pdf(build_pdf("Primeira pagina", "Segunda pagina"))

    assert [split.page_content for split in splits] == [
        "Primeira pagina",
        "Segunda pagina",
    ]
    assert [split.metadata["page"] for split in splits] == [0, 1]


def test_split_pdf_removes_null_characters(monkeypatch):
    replace_loader(monkeypatch, [Document(page_content="te\x00xto")])
    assert split_pdf(b"%PDF-")[0].page_content == "texto"


def test_split_pdf_discards_blank_chunks(monkeypatch):
    replace_loader(
        monkeypatch,
        [
            Document(page_content="  \n "),
            Document(page_content="\x00"),
            Document(page_content="texto"),
        ],
    )
    assert [split.page_content for split in split_pdf(b"%PDF-")] == ["texto"]


def test_split_pdf_without_text_returns_422(monkeypatch):
    replace_loader(monkeypatch, [Document(page_content="   ")])

    with pytest.raises(HTTPException) as error:
        split_pdf(b"%PDF-")

    assert error.value.status_code == 422
    assert error.value.detail == "O PDF não contém texto extraível."


def test_split_pdf_converts_read_errors_to_422(monkeypatch):
    def fail(_path):
        raise ValueError("detalhe interno")

    monkeypatch.setattr("app.services.documents.load_and_split", fail)

    with pytest.raises(HTTPException) as error:
        split_pdf(b"%PDF-")

    assert error.value.status_code == 422
    assert "detalhe interno" not in error.value.detail


def test_split_pdf_removes_the_temporary_file(monkeypatch):
    paths = []

    def capture(path):
        paths.append(Path(path))
        assert paths[0].read_bytes() == b"%PDF-conteudo"
        return [Document(page_content="texto")]

    monkeypatch.setattr("app.services.documents.load_and_split", capture)

    split_pdf(b"%PDF-conteudo")

    assert not paths[0].exists()


# clean_filename


def test_clean_filename_keeps_a_normal_name():
    assert clean_filename("curriculo.pdf") == "curriculo.pdf"


def test_clean_filename_accepts_none():
    assert clean_filename(None) is None


def test_clean_filename_removes_null_characters():
    assert clean_filename("doc\x00.pdf") == "doc.pdf"


def test_clean_filename_limits_the_length():
    assert len(clean_filename("a" * 1000)) == MAX_FILENAME_LENGTH


# build_sources


@pytest.mark.parametrize(("stored", "shown"), [(0, 1), (4, 5), (None, None)])
def test_build_sources_numbers_pages_from_one(stored, shown):
    chunk = Document(page_content="texto", metadata={"page": stored})
    assert build_sources([chunk])[0].page == shown


def test_build_sources_accepts_a_chunk_without_a_page():
    assert build_sources([Document(page_content="texto")])[0].page is None


def test_build_sources_limits_the_excerpt():
    chunk = Document(page_content="a" * (EXCERPT_LENGTH + 50))
    assert build_sources([chunk])[0].excerpt == "a" * EXCERPT_LENGTH


def test_build_sources_keeps_the_order():
    chunks = [Document(page_content="um"), Document(page_content="dois")]
    assert [source.excerpt for source in build_sources(chunks)] == ["um", "dois"]


def test_build_sources_without_context_returns_an_empty_list():
    assert build_sources([]) == []
