from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY
from app.security import (
    create_access_token,
    hash_password,
    read_access_token,
    verify_password,
)


def test_hash_does_not_contain_the_password():
    assert "minha-senha" not in hash_password("minha-senha")


def test_same_password_generates_different_hashes():
    assert hash_password("minha-senha") != hash_password("minha-senha")


def test_verify_accepts_the_correct_password():
    assert verify_password("minha-senha", hash_password("minha-senha")) is True


def test_verify_rejects_a_wrong_password():
    assert verify_password("outra-senha", hash_password("minha-senha")) is False


def test_verify_without_a_hash_returns_false():
    assert verify_password("minha-senha", None) is False


def test_verify_with_a_malformed_hash_returns_false():
    assert verify_password("minha-senha", "nao-e-um-hash") is False


def test_token_contains_the_user_id():
    user_id = uuid4()
    assert read_access_token(create_access_token(user_id)) == user_id


def test_token_expires_after_the_configured_time():
    payload = jwt.decode(
        create_access_token(uuid4()), JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
    )
    assert payload["exp"] - payload["iat"] == ACCESS_TOKEN_EXPIRE_MINUTES * 60


def future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=5)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="vazio"),
        pytest.param("nao-e-um-token", id="malformado"),
        pytest.param(
            jwt.encode(
                {
                    "sub": str(uuid4()),
                    "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
                },
                JWT_SECRET_KEY,
                algorithm=JWT_ALGORITHM,
            ),
            id="expirado",
        ),
        pytest.param(
            jwt.encode(
                {"sub": str(uuid4()), "exp": future()},
                "outra-chave-com-pelo-menos-32-caracteres",
                algorithm=JWT_ALGORITHM,
            ),
            id="outra-chave",
        ),
        pytest.param(
            jwt.encode({"sub": str(uuid4()), "exp": future()}, None, algorithm="none"),
            id="sem-assinatura",
        ),
        pytest.param(
            jwt.encode({"sub": str(uuid4())}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
            id="sem-exp",
        ),
        pytest.param(
            jwt.encode({"exp": future()}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
            id="sem-sub",
        ),
        pytest.param(
            jwt.encode(
                {"sub": "nao-e-uuid", "exp": future()},
                JWT_SECRET_KEY,
                algorithm=JWT_ALGORITHM,
            ),
            id="sub-invalido",
        ),
    ],
)
def test_invalid_tokens_return_none(token):
    assert read_access_token(token) is None


def test_tampered_token_returns_none():
    header, payload, signature = create_access_token(uuid4()).split(".")
    other_payload = create_access_token(uuid4()).split(".")[1]
    assert read_access_token(f"{header}.{other_payload}.{signature}") is None
