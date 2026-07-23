"""Belediye atık merkezleri tablosu (İBB / Konya / genişletilebilir).

Revision ID: n4d1e2f3a4b5
Revises: m3c0d1e2f4a5
"""

import sqlalchemy as sa
from alembic import op


revision = "n4d1e2f3a4b5"
down_revision = "m3c0d1e2f4a5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "municipal_waste_centers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("facility_type", sa.String(length=120), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("district", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("waste_types", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_name", sa.String(length=150), nullable=False),
        sa.Column("external_key", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_key", name="uq_mwc_source_external_key"),
    )
    op.create_index("ix_municipal_waste_centers_city", "municipal_waste_centers", ["city"])
    op.create_index("ix_municipal_waste_centers_source", "municipal_waste_centers", ["source"])
    op.create_index("ix_mwc_source_city", "municipal_waste_centers", ["source", "city"])
    op.create_index("ix_mwc_coords", "municipal_waste_centers", ["latitude", "longitude"])


def downgrade():
    op.drop_index("ix_mwc_coords", table_name="municipal_waste_centers")
    op.drop_index("ix_mwc_source_city", table_name="municipal_waste_centers")
    op.drop_index("ix_municipal_waste_centers_source", table_name="municipal_waste_centers")
    op.drop_index("ix_municipal_waste_centers_city", table_name="municipal_waste_centers")
    op.drop_table("municipal_waste_centers")
