"""subscription fields on users (Lemon Squeezy)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

COLS = [("subscription_id", sa.String(64)), ("subscription_status", sa.String(32)),
        ("subscription_renews_at", sa.DateTime(timezone=True)), ("subscription_ends_at", sa.DateTime(timezone=True)),
        ("subscription_updated_at", sa.DateTime(timezone=True)), ("customer_portal_url", sa.String(512))]


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        for name, typ in COLS:
            b.add_column(sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        for name, _ in reversed(COLS):
            b.drop_column(name)
