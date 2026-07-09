"""Phase 3: AI health log tablosu.

Revision ID: d3f9a5b7c1e4
Revises: c2e8f4a6b0d3
"""

from alembic import op
import sqlalchemy as sa


revision = "d3f9a5b7c1e4"
down_revision = "c2e8f4a6b0d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_moderasyon_health_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("request_type", sa.String(length=30), nullable=False, server_default="vision"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=30), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_moderasyon_health_log_model", "ai_moderasyon_health_log", ["model_name"])
    op.create_index("ix_ai_moderasyon_health_log_success", "ai_moderasyon_health_log", ["success"])
    op.create_index("ix_ai_moderasyon_health_log_created_at", "ai_moderasyon_health_log", ["created_at"])


def downgrade():
    op.drop_table("ai_moderasyon_health_log")
