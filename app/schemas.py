from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from app.config import (
    MAX_PASSWORD_LENGTH,
    MAX_QUESTION_LENGTH,
    MIN_PASSWORD_LENGTH,
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterRequest(BaseModel):
    email: Annotated[EmailStr, AfterValidator(normalize_email)]
    password: Annotated[
        str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    ]


class UserResponse(BaseModel):
    id: UUID
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DocumentResponse(BaseModel):
    id: UUID
    filename: str | None
    chunks: int
    created_at: datetime


class QuestionRequest(BaseModel):
    question: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH
        ),
    ]


class Source(BaseModel):
    page: int | None
    excerpt: str


class AnswerResponse(BaseModel):
    answer: str
    sources: list[Source]
