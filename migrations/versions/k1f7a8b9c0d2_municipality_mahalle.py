"""Belediye paneli: User.mahalle alanı.

Revision ID: k1f7a8b9c0d2
Revises: j0e6f7a8b9c1
"""

import sqlalchemy as sa
from alembic import op


revision = "k1f7a8b9c0d2"
down_revision = "j0e6f7a8b9c1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mahalle", sa.String(length=120), nullable=True))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("mahalle")
