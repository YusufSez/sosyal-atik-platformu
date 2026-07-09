"""Production performance indexes.

Revision ID: e4a1b8c2d5f6
Revises: d3f9a5b7c1e4
"""

from alembic import op


revision = "e4a1b8c2d5f6"
down_revision = "d3f9a5b7c1e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_kaynak_moderation_status", "kaynak", ["moderation_status"], unique=False)
    op.create_index("ix_atik_moderation_status", "atik", ["moderation_status"], unique=False)
    op.create_index("ix_ilan_resim_kaynak_id", "ilan_resim", ["kaynak_id"], unique=False)
    op.create_index("ix_ilan_resim_atik_id", "ilan_resim", ["atik_id"], unique=False)


def downgrade():
    op.drop_index("ix_ilan_resim_atik_id", table_name="ilan_resim")
    op.drop_index("ix_ilan_resim_kaynak_id", table_name="ilan_resim")
    op.drop_index("ix_atik_moderation_status", table_name="atik")
    op.drop_index("ix_kaynak_moderation_status", table_name="kaynak")
