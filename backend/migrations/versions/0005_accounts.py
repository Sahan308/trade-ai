"""accounts and server-side trial

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False, server_default="trial"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "signal_unlocks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "signal_id"),
    )
    op.create_index("ix_signal_unlocks_user_id", "signal_unlocks", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_signal_unlocks_user_id", "signal_unlocks")
    op.drop_table("signal_unlocks")
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")
