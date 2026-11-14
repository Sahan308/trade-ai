"""signals table

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(256), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("market", sa.String(16), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("side", sa.String(16), nullable=False),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("config_hash", sa.String(32), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_signals_created_at", "signals", ["created_at"])
    op.create_index("ix_signals_symbol", "signals", ["symbol"])
    op.create_index("ix_signals_side", "signals", ["side"])


def downgrade() -> None:
    op.drop_index("ix_signals_side", table_name="signals")
    op.drop_index("ix_signals_symbol", table_name="signals")
    op.drop_index("ix_signals_created_at", table_name="signals")
    op.drop_table("signals")
