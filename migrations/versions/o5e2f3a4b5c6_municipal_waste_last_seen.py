"""municipal_waste_centers: last_seen_at soft-delete alanı.

Revision ID: o5e2f3a4b5c6
Revises: n4d1e2f3a4b5
"""

import sqlalchemy as sa
from alembic import op


revision = "o5e2f3a4b5c6"
down_revision = "n4d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("municipal_waste_centers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_municipal_waste_centers_last_seen_at", ["last_seen_at"])

    # Mevcut kayıtlara 90 günlük grace için last_seen_at ver
    op.execute(
        sa.text(
            "UPDATE municipal_waste_centers "
            "SET last_seen_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
            "WHERE last_seen_at IS NULL"
        )
    )


def downgrade():
    with op.batch_alter_table("municipal_waste_centers", schema=None) as batch_op:
        batch_op.drop_index("ix_municipal_waste_centers_last_seen_at")
        batch_op.drop_column("last_seen_at")
