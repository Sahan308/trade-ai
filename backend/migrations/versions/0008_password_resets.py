"""password reset tokens

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("password_resets",
                    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_resets_user_id", "password_resets"); op.drop_table("password_resets")
