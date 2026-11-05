import pytest

from app.config import CHUNK_SIZE
from app.rag.loader import load_and_split
from tests.conftest import build_pdf


@pytest.fixture
def pdf_path(tmp_path):
    def _pdf_path(*pages: str) -> str:
        path = tmp_path / "teste.pdf"
        path.write_bytes(build_pdf(*pages))
        return str(path)

    return _pdf_path


def long_text(words: int) -> str:
    return " ".join(f"palavra{i}" for i in range(words))


def test_each_page_generates_chunks_with_its_number(pdf_path):
    splits = load_and_split(pdf_path("Primeira pagina", "Segunda pagina"))

    assert [split.page_content for split in splits] == [
        "Primeira pagina",
        "Segunda pagina",
    ]
    assert [split.metadata["page"] for split in splits] == [0, 1]


def test_long_page_is_split_within_the_default_size(pdf_path):
    splits = load_and_split(pdf_path(long_text(1000)))

    assert len(splits) > 1
    assert all(len(split.page_content) <= CHUNK_SIZE for split in splits)


def test_custom_sizes_are_respected(pdf_path):
    splits = load_and_split(pdf_path(long_text(100)), chunk_size=100, chunk_overlap=0)

    assert len(splits) > 1
    assert all(len(split.page_content) <= 100 for split in splits)


def test_neighboring_chunks_share_the_overlap(pdf_path):
    splits = load_and_split(pdf_path(long_text(100)), chunk_size=100, chunk_overlap=30)

    first_word_of_second_chunk = splits[1].page_content.split()[0]
    assert first_word_of_second_chunk in splits[0].page_content


def test_no_word_is_lost_when_splitting(pdf_path):
    splits = load_and_split(pdf_path(long_text(100)), chunk_size=100, chunk_overlap=0)

    words = " ".join(split.page_content for split in splits).split()
    assert words == long_text(100).split()


def test_page_without_text_generates_no_chunks(pdf_path):
    assert load_and_split(pdf_path("")) == []


def test_missing_file_raises_an_error(tmp_path):
    with pytest.raises(ValueError):
        load_and_split(str(tmp_path / "nao-existe.pdf"))
