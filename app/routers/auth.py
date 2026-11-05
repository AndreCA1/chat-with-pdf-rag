import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, MAX_PASSWORD_LENGTH
from app.database import SessionLocal
from app.models import User
from app.schemas import (
    RegisterRequest,
    TokenResponse,
    UserResponse,
    normalize_email,
)
from app.security import create_access_token, hash_password, verify_password
from app.services.login_limiter import clear_login_attempts, reserve_login_attempt

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma conta",
    responses={409: {"description": "E-mail já cadastrado"}},
)
def register(body: RegisterRequest):
    user = User(email=body.email, password_hash=hash_password(body.password))
    with SessionLocal() as session:
        session.add(user)
        try:
            session.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "E-mail já cadastrado."
            ) from exc
    return UserResponse(id=user.id, email=user.email)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Entra na conta e devolve um token de acesso",
    description="Informe o e-mail no campo `username`, como define o padrão OAuth2.",
    responses={
        401: {"description": "E-mail ou senha incorretos"},
        429: {"description": "Limite de tentativas de login atingido"},
    },
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], response: Response):
    email = normalize_email(form.username)

    retry_after = reserve_login_attempt(email)
    if retry_after is not None:
        minutes = math.ceil(retry_after / 60)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Muitas tentativas de login. Tente novamente em {minutes} min.",
            headers={"Retry-After": str(retry_after)},
        )

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))

    # A senha é sempre verificada, para que o tempo de resposta não revele se o
    # e-mail existe. Senhas acima do limite nunca foram cadastradas.
    password_ok = verify_password(
        form.password[:MAX_PASSWORD_LENGTH + 1], user.password_hash if user else None
    )
    if not password_ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clear_login_attempts(email)

    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
