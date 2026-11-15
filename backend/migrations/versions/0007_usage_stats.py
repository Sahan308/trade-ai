"""privacy-friendly usage stats

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("page_views",
                    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                    sa.Column("day", sa.String(10), nullable=False), sa.Column("path", sa.String(64), nullable=False),
                    sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
                    sa.Column("visitors", sa.Integer(), nullable=False, server_default="0"),
                    sa.UniqueConstraint("day", "path"))
    op.create_index("ix_page_views_day", "page_views", ["day"])
    op.create_table("daily_visitors",
                    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                    sa.Column("day", sa.String(10), nullable=False), sa.Column("path", sa.String(64), nullable=False),
                    sa.Column("visitor", sa.String(32), nullable=False),
                    sa.UniqueConstraint("day", "path", "visitor"))
    op.create_index("ix_daily_visitors_day", "daily_visitors", ["day"])


def downgrade() -> None:
    op.drop_index("ix_daily_visitors_day", "daily_visitors"); op.drop_table("daily_visitors")
    op.drop_index("ix_page_views_day", "page_views"); op.drop_table("page_views")
