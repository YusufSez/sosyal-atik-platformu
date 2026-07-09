"""İlan moderasyon analiz geçmişi, timeline ve admin notları.

Revision ID: a9c3e5f7b1d2
Revises: f8a4b2c6d7e9
"""

from alembic import op
import sqlalchemy as sa


revision = "a9c3e5f7b1d2"
down_revision = "f8a4b2c6d7e9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ilan_moderasyon_analiz",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tur", sa.String(length=10), nullable=False),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("atik_id", sa.Integer(), nullable=True),
        sa.Column("analysis_version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("initial_risk", sa.Integer(), nullable=True),
        sa.Column("final_risk", sa.Integer(), nullable=True),
        sa.Column("risk_adjustment", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("purpose", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_recyclable", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("matched_rules_json", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("moderation_status", sa.String(length=30), nullable=False),
        sa.Column("whitelist_applied", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("risk_adjustment_reason", sa.Text(), nullable=True),
        sa.Column("text_analysis_json", sa.Text(), nullable=True),
        sa.Column("vision_analysis_json", sa.Text(), nullable=True),
        sa.Column("photo_analyses_json", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=30), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["atik_id"], ["atik.id"]),
        sa.ForeignKeyConstraint(["kaynak_id"], ["kaynak.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ilan_moderasyon_analiz_tur", "ilan_moderasyon_analiz", ["tur"])
    op.create_index("ix_ilan_moderasyon_analiz_is_current", "ilan_moderasyon_analiz", ["is_current"])
    op.create_index("ix_ilan_moderasyon_analiz_kaynak_id", "ilan_moderasyon_analiz", ["kaynak_id"])
    op.create_index("ix_ilan_moderasyon_analiz_atik_id", "ilan_moderasyon_analiz", ["atik_id"])
    op.create_index("ix_ilan_moderasyon_analiz_created_at", "ilan_moderasyon_analiz", ["created_at"])

    op.create_table(
        "ilan_moderasyon_timeline",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tur", sa.String(length=10), nullable=False),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("atik_id", sa.Integer(), nullable=True),
        sa.Column("analiz_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["analiz_id"], ["ilan_moderasyon_analiz.id"]),
        sa.ForeignKeyConstraint(["atik_id"], ["atik.id"]),
        sa.ForeignKeyConstraint(["kaynak_id"], ["kaynak.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ilan_moderasyon_timeline_tur", "ilan_moderasyon_timeline", ["tur"])
    op.create_index("ix_ilan_moderasyon_timeline_event_type", "ilan_moderasyon_timeline", ["event_type"])
    op.create_index("ix_ilan_moderasyon_timeline_created_at", "ilan_moderasyon_timeline", ["created_at"])

    op.create_table(
        "ilan_moderasyon_not",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tur", sa.String(length=10), nullable=False),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("atik_id", sa.Integer(), nullable=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["atik_id"], ["atik.id"]),
        sa.ForeignKeyConstraint(["kaynak_id"], ["kaynak.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ilan_moderasyon_not_tur", "ilan_moderasyon_not", ["tur"])
    op.create_index("ix_ilan_moderasyon_not_created_at", "ilan_moderasyon_not", ["created_at"])


def downgrade():
    op.drop_table("ilan_moderasyon_not")
    op.drop_table("ilan_moderasyon_timeline")
    op.drop_table("ilan_moderasyon_analiz")
