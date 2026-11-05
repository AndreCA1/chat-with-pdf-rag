from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.dependencies import get_current_user
from app.security import create_access_token


def test_valid_token_returns_the_user(user):
    assert get_current_user(create_access_token(user.id)).id == user.id


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(None, id="ausente"),
        pytest.param("token-invalido", id="invalido"),
        pytest.param(create_access_token(uuid4()), id="usuario-inexistente"),
    ],
)
def test_all_failures_get_the_same_response(token):
    with pytest.raises(HTTPException) as error:
        get_current_user(token)

    assert error.value.status_code == 401
    assert error.value.detail == "Token de acesso ausente, inválido ou expirado."
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
