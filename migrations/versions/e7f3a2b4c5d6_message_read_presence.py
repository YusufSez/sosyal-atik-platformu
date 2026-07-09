"""Mesaj okunma zamanı ve kullanıcı son görülme.

Revision ID: e7f3a2b4c5d6
Revises: d6e8f2a1b3c4
"""

from alembic import op
import sqlalchemy as sa


revision = "e7f3a2b4c5d6"
down_revision = "d6e8f2a1b3c4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("mesaj") as batch:
        batch.add_column(sa.Column("read_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("last_seen", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("user") as batch:
        batch.drop_column("last_seen")
    with op.batch_alter_table("mesaj") as batch:
        batch.drop_column("read_at")
