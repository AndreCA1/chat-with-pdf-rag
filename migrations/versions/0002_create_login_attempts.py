"""Cria a tabela que limita as tentativas de login

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("email_hash", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_login_attempts_window_started_at",
        "login_attempts",
        ["window_started_at"],
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
