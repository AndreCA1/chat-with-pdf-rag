# =============================================================================
# login_limiter.py — Limite de tentativas de login
# =============================================================================
# Responsabilidade única: contar as tentativas de login por e-mail no banco.
#
# O limite vale também para e-mails sem conta, para não revelar quais existem.
# Cada tentativa é contada antes da verificação da senha, em uma única operação
# atômica. Assim, requisições simultâneas não conseguem ultrapassar o limite.

import hashlib
import math
from datetime import timedelta

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from config import LOGIN_ATTEMPT_WINDOW_MINUTES, MAX_LOGIN_ATTEMPTS
from database import SessionLocal
from models import LoginAttempt

WINDOW = timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES)


def hash_email(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()


def reserve_login_attempt(email: str) -> int | None:
    """Conta uma tentativa. Se o limite foi atingido, devolve os segundos de espera."""
    now = func.now()
    window_expired = LoginAttempt.window_started_at <= now - WINDOW

    statement = (
        insert(LoginAttempt)
        .values(email_hash=hash_email(email), attempts=1, window_started_at=now)
        .on_conflict_do_update(
            index_elements=[LoginAttempt.email_hash],
            set_={
                "attempts": case(
                    (window_expired, 1), else_=LoginAttempt.attempts + 1
                ),
                "window_started_at": case(
                    (window_expired, now), else_=LoginAttempt.window_started_at
                ),
            },
        )
        .returning(
            LoginAttempt.attempts,
            func.extract("epoch", LoginAttempt.window_started_at + WINDOW - now),
        )
    )

    # Registros vencidos são removidos para a tabela não crescer sem limite.
    # SKIP LOCKED evita que logins simultâneos esperem uns pelos outros.
    expired_rows = (
        select(LoginAttempt.email_hash)
        .where(LoginAttempt.window_started_at <= now - WINDOW)
        .with_for_update(skip_locked=True)
    )

    with SessionLocal() as session:
        session.execute(
            delete(LoginAttempt).where(LoginAttempt.email_hash.in_(expired_rows))
        )
        attempts, seconds_left = session.execute(statement).one()
        session.commit()

    if attempts > MAX_LOGIN_ATTEMPTS:
        return max(1, math.ceil(seconds_left))
    return None


def clear_login_attempts(email: str) -> None:
    """Zera a contagem depois de um login bem-sucedido."""
    with SessionLocal() as session:
        session.execute(
            delete(LoginAttempt).where(LoginAttempt.email_hash == hash_email(email))
        )
        session.commit()
