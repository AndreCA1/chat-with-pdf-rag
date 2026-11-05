import hashlib
from datetime import timedelta

from sqlalchemy import func, select, update

from app.config import LOGIN_ATTEMPT_WINDOW_MINUTES, MAX_LOGIN_ATTEMPTS
from app.database import SessionLocal
from app.models import LoginAttempt
from app.services.login_limiter import (
    clear_login_attempts,
    hash_email,
    reserve_login_attempt,
)

EMAIL = "ana@exemplo.com"
OTHER_EMAIL = "bruno@exemplo.com"


def stored_attempts(email: str) -> int | None:
    with SessionLocal() as session:
        return session.scalar(
            select(LoginAttempt.attempts).where(
                LoginAttempt.email_hash == hash_email(email)
            )
        )


def expire_window(email: str) -> None:
    with SessionLocal() as session:
        session.execute(
            update(LoginAttempt)
            .where(LoginAttempt.email_hash == hash_email(email))
            .values(
                window_started_at=func.now()
                - timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES + 1)
            )
        )
        session.commit()


def use_all_attempts(email: str) -> None:
    for _ in range(MAX_LOGIN_ATTEMPTS):
        assert reserve_login_attempt(email) is None


def test_hash_email_is_a_sha256():
    assert hash_email(EMAIL) == hashlib.sha256(EMAIL.encode()).hexdigest()


def test_email_is_not_stored_in_plain_text():
    reserve_login_attempt(EMAIL)

    with SessionLocal() as session:
        attempt = session.scalar(select(LoginAttempt))
    assert attempt.email_hash == hash_email(EMAIL)
    assert EMAIL not in attempt.email_hash


def test_attempts_up_to_the_limit_are_allowed():
    use_all_attempts(EMAIL)
    assert stored_attempts(EMAIL) == MAX_LOGIN_ATTEMPTS


def test_attempt_above_the_limit_returns_the_wait_time():
    use_all_attempts(EMAIL)

    seconds = reserve_login_attempt(EMAIL)

    assert 0 < seconds <= LOGIN_ATTEMPT_WINDOW_MINUTES * 60


def test_attempts_are_counted_per_email():
    use_all_attempts(EMAIL)
    assert reserve_login_attempt(OTHER_EMAIL) is None
    assert stored_attempts(OTHER_EMAIL) == 1


def test_clear_resets_only_the_given_email():
    reserve_login_attempt(EMAIL)
    reserve_login_attempt(OTHER_EMAIL)

    clear_login_attempts(EMAIL)

    assert stored_attempts(EMAIL) is None
    assert stored_attempts(OTHER_EMAIL) == 1


def test_clear_without_attempts_does_nothing():
    clear_login_attempts(EMAIL)
    assert stored_attempts(EMAIL) is None


def test_count_restarts_after_the_window_expires():
    use_all_attempts(EMAIL)
    assert reserve_login_attempt(EMAIL) is not None
    expire_window(EMAIL)

    assert reserve_login_attempt(EMAIL) is None
    assert stored_attempts(EMAIL) == 1


def test_expired_attempts_from_other_emails_are_removed():
    reserve_login_attempt(OTHER_EMAIL)
    expire_window(OTHER_EMAIL)

    reserve_login_attempt(EMAIL)

    assert stored_attempts(OTHER_EMAIL) is None
    assert stored_attempts(EMAIL) == 1


def test_active_attempts_from_other_emails_are_kept():
    reserve_login_attempt(OTHER_EMAIL)

    reserve_login_attempt(EMAIL)

    assert stored_attempts(OTHER_EMAIL) == 1
