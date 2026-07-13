"""Kurumsal Kaynak Pazarı tabloları.

Revision ID: l2a8b9c0d1e3
Revises: k1f7a8b9c0d2
"""

import sqlalchemy as sa
from alembic import op


revision = "l2a8b9c0d1e3"
down_revision = "k1f7a8b9c0d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketplace_listing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publisher_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("baslik", sa.String(length=150), nullable=False),
        sa.Column("aciklama", sa.Text(), nullable=False),
        sa.Column("kategori", sa.String(length=50), nullable=False),
        sa.Column("miktar", sa.Float(), nullable=True),
        sa.Column("birim", sa.String(length=30), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("il", sa.String(length=100), nullable=True),
        sa.Column("ilce", sa.String(length=100), nullable=True),
        sa.Column("durum", sa.String(length=20), nullable=False, server_default="yayinda"),
        sa.Column("accepted_offer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_marketplace_listing_publisher_id", "marketplace_listing", ["publisher_id"])
    op.create_index("ix_marketplace_listing_durum", "marketplace_listing", ["durum"])
    op.create_index("ix_marketplace_listing_created_at", "marketplace_listing", ["created_at"])

    op.create_table(
        "marketplace_offer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("marketplace_listing.id"), nullable=False),
        sa.Column("offerer_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("mesaj", sa.Text(), nullable=True),
        sa.Column("miktar", sa.Float(), nullable=True),
        sa.Column("durum", sa.String(length=20), nullable=False, server_default="bekliyor"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_marketplace_offer_listing_id", "marketplace_offer", ["listing_id"])
    op.create_index("ix_marketplace_offer_offerer_id", "marketplace_offer", ["offerer_id"])
    op.create_index("ix_marketplace_offer_durum", "marketplace_offer", ["durum"])
    op.create_index("ix_marketplace_offer_created_at", "marketplace_offer", ["created_at"])

    op.create_table(
        "marketplace_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("marketplace_listing.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("marketplace_offer.id"), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_marketplace_event_listing_id", "marketplace_event", ["listing_id"])
    op.create_index("ix_marketplace_event_action", "marketplace_event", ["action"])
    op.create_index("ix_marketplace_event_created_at", "marketplace_event", ["created_at"])


def downgrade():
    op.drop_table("marketplace_event")
    op.drop_table("marketplace_offer")
    op.drop_table("marketplace_listing")
