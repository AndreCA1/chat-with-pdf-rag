import pytest
from sqlalchemy import select

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    MAX_LOGIN_ATTEMPTS,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
)
from app.database import SessionLocal
from app.models import User
from app.security import read_access_token, verify_password
from tests.conftest import DEFAULT_PASSWORD


def register(client, email="nova@exemplo.com", password=DEFAULT_PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client, email="ana@exemplo.com", password=DEFAULT_PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_register_creates_the_account(client):
    response = register(client)

    assert response.status_code == 201
    assert response.json()["email"] == "nova@exemplo.com"
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "nova@exemplo.com"))
    assert str(user.id) == response.json()["id"]


def test_register_stores_only_the_password_hash(client):
    response = register(client)

    with SessionLocal() as session:
        user = session.scalar(select(User))
    assert user.password_hash != DEFAULT_PASSWORD
    assert verify_password(DEFAULT_PASSWORD, user.password_hash)
    assert set(response.json()) == {"id", "email"}


def test_register_normalizes_the_email(client):
    assert register(client, email="Nova@Exemplo.COM").json()["email"] == (
        "nova@exemplo.com"
    )


def test_register_rejects_a_duplicate_email(client):
    register(client)

    response = register(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "E-mail já cadastrado."


def test_register_detects_a_duplicate_with_different_case(client):
    register(client)
    assert register(client, email="NOVA@exemplo.com").status_code == 409


@pytest.mark.parametrize(
    ("email", "password"),
    [
        pytest.param("sem-arroba", DEFAULT_PASSWORD, id="email-invalido"),
        pytest.param(
            "nova@exemplo.com", "a" * (MIN_PASSWORD_LENGTH - 1), id="senha-curta"
        ),
        pytest.param(
            "nova@exemplo.com", "a" * (MAX_PASSWORD_LENGTH + 1), id="senha-longa"
        ),
    ],
)
def test_register_validates_the_data(client, email, password):
    assert register(client, email=email, password=password).status_code == 422


def test_login_returns_a_valid_token(client, user):
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert read_access_token(body["access_token"]) == user.id
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_login_response_is_not_cached(client, user):
    assert login(client).headers["Cache-Control"] == "no-store"


def test_login_ignores_email_case_and_spaces(client, user):
    assert login(client, email="  ANA@exemplo.com ").status_code == 200


def test_registered_account_can_log_in(client):
    register(client)
    assert login(client, email="nova@exemplo.com").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_response(client, user):
    wrong_password = login(client, password="senha-incorreta")
    unknown_email = login(client, email="ninguem@exemplo.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.headers["WWW-Authenticate"] == "Bearer"


def test_login_rejects_a_password_above_the_limit(client, make_user):
    make_user(password="a" * MAX_PASSWORD_LENGTH)

    response = login(client, password="a" * (MAX_PASSWORD_LENGTH + 1))

    assert response.status_code == 401


def test_login_is_blocked_after_too_many_attempts(client, user):
    for _ in range(MAX_LOGIN_ATTEMPTS):
        assert login(client, password="senha-incorreta").status_code == 401

    response = login(client)  # bloqueia mesmo com a senha correta

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert "Muitas tentativas" in response.json()["detail"]


def test_login_block_counts_variations_of_the_same_email(client, user):
    for _ in range(MAX_LOGIN_ATTEMPTS):
        login(client, email="ANA@exemplo.com", password="senha-incorreta")

    assert login(client).status_code == 429


def test_login_block_does_not_affect_other_accounts(client, make_user):
    make_user()
    make_user("bruno@exemplo.com")
    for _ in range(MAX_LOGIN_ATTEMPTS + 1):
        login(client, password="senha-incorreta")

    assert login(client, email="bruno@exemplo.com").status_code == 200


def test_successful_login_before_the_limit_resets_the_count(client, user):
    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        login(client, password="senha-incorreta")
    assert login(client).status_code == 200

    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        login(client, password="senha-incorreta")
    assert login(client).status_code == 200


def test_null_character_in_the_email_gets_the_unknown_email_response(client, user):
    response = login(client, email="ana\x00@exemplo.com")

    assert response.status_code == 401
    assert response.json() == login(client, email="ninguem@exemplo.com").json()


def test_null_character_in_the_email_counts_as_an_attempt(client):
    email = "ana\x00@exemplo.com"
    for _ in range(MAX_LOGIN_ATTEMPTS):
        assert login(client, email=email).status_code == 401

    assert login(client, email=email).status_code == 429


def test_null_character_in_the_password_is_rejected(client, user):
    assert login(client, password="senha\x00incorreta").status_code == 401
