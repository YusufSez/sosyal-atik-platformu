"""Sistem ayarları tablosu (Demo Modu vb.).

Revision ID: m3c0d1e2f4a5
Revises: l2a8b9c0d1e3
"""

import sqlalchemy as sa
from alembic import op


revision = "m3c0d1e2f4a5"
down_revision = "l2a8b9c0d1e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_setting",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
    )


def downgrade():
    op.drop_table("system_setting")
