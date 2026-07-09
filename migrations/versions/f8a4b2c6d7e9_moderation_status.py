"""İlan AI moderasyon durumu alanları.

Revision ID: f8a4b2c6d7e9
Revises: e7f3a2b4c5d6
"""

from alembic import op
import sqlalchemy as sa


revision = "f8a4b2c6d7e9"
down_revision = "e7f3a2b4c5d6"
branch_labels = None
depends_on = None


def _add_moderation_columns(table: str):
    with op.batch_alter_table(table) as batch:
        batch.add_column(
            sa.Column("moderation_status", sa.String(length=30), nullable=False, server_default="approved")
        )
        batch.add_column(sa.Column("moderation_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("ai_risk_score", sa.Integer(), nullable=True))


def upgrade():
    _add_moderation_columns("kaynak")
    _add_moderation_columns("atik")


def downgrade():
    for table in ("atik", "kaynak"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("ai_risk_score")
            batch.drop_column("moderation_reason")
            batch.drop_column("moderation_status")
