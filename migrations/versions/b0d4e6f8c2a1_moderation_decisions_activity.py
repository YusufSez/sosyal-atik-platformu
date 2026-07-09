"""Phase 1: moderasyon karar + activity log tabloları.

Revision ID: b0d4e6f8c2a1
Revises: a9c3e5f7b1d2
"""

from alembic import op
import sqlalchemy as sa


revision = "b0d4e6f8c2a1"
down_revision = "a9c3e5f7b1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ilan_moderasyon_karar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tur", sa.String(length=10), nullable=False),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("atik_id", sa.Integer(), nullable=True),
        sa.Column("analiz_id", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("ai_decision", sa.String(length=30), nullable=False),
        sa.Column("admin_decision", sa.String(length=30), nullable=False),
        sa.Column("decision_match", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("override", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("decision_version", sa.Integer(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("decision_time", sa.DateTime(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("purpose", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["analiz_id"], ["ilan_moderasyon_analiz.id"]),
        sa.ForeignKeyConstraint(["atik_id"], ["atik.id"]),
        sa.ForeignKeyConstraint(["kaynak_id"], ["kaynak.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ilan_moderasyon_karar_tur", "ilan_moderasyon_karar", ["tur"])
    op.create_index("ix_ilan_moderasyon_karar_override", "ilan_moderasyon_karar", ["override"])
    op.create_index("ix_ilan_moderasyon_karar_decision_time", "ilan_moderasyon_karar", ["decision_time"])

    op.create_table(
        "ilan_moderasyon_activity_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tur", sa.String(length=10), nullable=True),
        sa.Column("kaynak_id", sa.Integer(), nullable=True),
        sa.Column("atik_id", sa.Integer(), nullable=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["atik_id"], ["atik.id"]),
        sa.ForeignKeyConstraint(["kaynak_id"], ["kaynak.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ilan_moderasyon_activity_log_action", "ilan_moderasyon_activity_log", ["action"])
    op.create_index("ix_ilan_moderasyon_activity_log_created_at", "ilan_moderasyon_activity_log", ["created_at"])


def downgrade():
    op.drop_table("ilan_moderasyon_activity_log")
    op.drop_table("ilan_moderasyon_karar")
