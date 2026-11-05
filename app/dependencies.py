from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.database import SessionLocal
from app.models import User
from app.security import read_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False) #token ausente recebe a mesma resposta que um token invalido

def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> User:
    """Identifica o usuário pelo token, com a mesma resposta para qualquer falha."""
    user_id = read_access_token(token) if token else None
    user = None
    if user_id is not None:
        with SessionLocal() as session:
            user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token de acesso ausente, inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
