# Gera e verifica hashes de senha (Argon2) e tokens de sessão (JWT).

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY

if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
    raise RuntimeError("Defina JWT_SECRET_KEY no .env, com pelo menos 32 caracteres.")

password_hasher = PasswordHasher()

# Verificado quando o e-mail não existe, para que o tempo de resposta do login
# não revele quais e-mails estão cadastrados.
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Confere a senha. Sem hash cadastrado, gasta o mesmo tempo e retorna False."""
    try:
        password_hasher.verify(password_hash or DUMMY_PASSWORD_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def read_access_token(token: str) -> UUID | None:
    """Devolve o ID do usuário, ou None se o token for inválido ou tiver expirado."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None
