"""Kullanıcı ad ve soyad alanları.

Revision ID: i9d5e6f7a8b0
Revises: h8c4d5e6f7a8
"""

import sqlalchemy as sa
from alembic import op


revision = "i9d5e6f7a8b0"
down_revision = "h8c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ad", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("soyad", sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("soyad")
        batch_op.drop_column("ad")
