"""signal lifecycle events, alerts, signals.outcome

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("signals") as b:
        b.add_column(sa.Column("outcome", sa.JSON(), nullable=True))
    op.create_table(
        "signal_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.JSON(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("signal_id", "seq"),
    )
    op.create_index("ix_signal_events_signal_id", "signal_events", ["signal_id"])
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
    )
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_signal_id", "alerts", ["signal_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_signal_id", table_name="alerts")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_signal_events_signal_id", table_name="signal_events")
    op.drop_table("signal_events")
    with op.batch_alter_table("signals") as b:
        b.drop_column("outcome")
