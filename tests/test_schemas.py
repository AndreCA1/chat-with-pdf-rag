import pytest
from pydantic import ValidationError

from app.config import MAX_PASSWORD_LENGTH, MAX_QUESTION_LENGTH, MIN_PASSWORD_LENGTH
from app.schemas import QuestionRequest, RegisterRequest, normalize_email


def test_normalize_email_removes_spaces_and_uppercase():
    assert normalize_email("  Ana@Exemplo.COM ") == "ana@exemplo.com"


def test_register_request_normalizes_the_email():
    body = RegisterRequest(email="Ana@Exemplo.COM", password="senha-segura")
    assert body.email == "ana@exemplo.com"


@pytest.mark.parametrize("email", ["", "sem-arroba", "ana@", "@exemplo.com"])
def test_register_request_rejects_invalid_emails(email):
    with pytest.raises(ValidationError):
        RegisterRequest(email=email, password="senha-segura")


@pytest.mark.parametrize("length", [MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH])
def test_register_request_accepts_passwords_at_the_limits(length):
    body = RegisterRequest(email="ana@exemplo.com", password="a" * length)
    assert len(body.password) == length


@pytest.mark.parametrize("length", [MIN_PASSWORD_LENGTH - 1, MAX_PASSWORD_LENGTH + 1])
def test_register_request_rejects_passwords_outside_the_limits(length):
    with pytest.raises(ValidationError):
        RegisterRequest(email="ana@exemplo.com", password="a" * length)


def test_question_request_removes_surrounding_spaces():
    assert QuestionRequest(question="  Qual o tema?  ").question == "Qual o tema?"


def test_question_request_accepts_the_maximum_length():
    question = "a" * MAX_QUESTION_LENGTH
    assert QuestionRequest(question=question).question == question


@pytest.mark.parametrize("question", ["", "    ", "a" * (MAX_QUESTION_LENGTH + 1)])
def test_question_request_rejects_empty_or_long_questions(question):
    with pytest.raises(ValidationError):
        QuestionRequest(question=question)
