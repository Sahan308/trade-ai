"""push subscriptions and email-alert opt-in

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("email_alerts", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("push_subscriptions",
                    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                    sa.Column("endpoint", sa.String(1024), nullable=False, unique=True),
                    sa.Column("p256dh", sa.String(255), nullable=False), sa.Column("auth", sa.String(255), nullable=False),
                    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    with op.batch_alter_table("users") as b:
        b.drop_column("email_alerts")
