import hashlib
import math
from datetime import timedelta

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import LOGIN_ATTEMPT_WINDOW_MINUTES, MAX_LOGIN_ATTEMPTS
from app.database import SessionLocal
from app.models import LoginAttempt

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

    expired_rows = (
        select(LoginAttempt.email_hash)
        .where(LoginAttempt.window_started_at <= now - WINDOW)
        .with_for_update(skip_locked=True) # evita que logins simultâneos esperem uns pelos outros
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
