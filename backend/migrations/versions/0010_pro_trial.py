"""7-day Pro trial (replaces the 3-signal unlock trial)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-15
"""
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))
    # Existing accounts get a fresh 7-day Pro trial from the switch-over.
    users = sa.table("users", sa.column("trial_ends_at", sa.DateTime(timezone=True)))
    op.execute(users.update().values(trial_ends_at=datetime.now(timezone.utc) + timedelta(days=7)))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("trial_ends_at")
