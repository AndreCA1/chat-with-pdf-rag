from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import func, inspect, select

from app.database import SessionLocal, engine
from app.models import Base, Chunk, Document, User


def test_migrations_match_the_models():
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_removes_the_tables_and_upgrade_recreates_them(alembic_config):
    application_tables = {"users", "documents", "chunks", "login_attempts"}
    try:
        command.downgrade(alembic_config, "base")
        engine.dispose()
        assert not application_tables & set(inspect(engine).get_table_names())
    finally:
        command.upgrade(alembic_config, "head")
        engine.dispose()

    assert application_tables <= set(inspect(engine).get_table_names())


def test_deleting_a_user_removes_documents_and_chunks(user, auth_headers, upload):
    assert upload(auth_headers).status_code == 201

    with SessionLocal() as session:
        session.delete(session.get(User, user.id))
        session.commit()

    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(Chunk)) == 0
