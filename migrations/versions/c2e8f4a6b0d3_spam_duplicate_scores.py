"""Phase 2: spam score + duplicate detection alanları.

Revision ID: c2e8f4a6b0d3
Revises: b0d4e6f8c2a1
"""

from alembic import op
import sqlalchemy as sa


revision = "c2e8f4a6b0d3"
down_revision = "b0d4e6f8c2a1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ilan_moderasyon_analiz", schema=None) as batch_op:
        batch_op.add_column(sa.Column("spam_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("duplicate_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("spam_reasons_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("duplicate_reasons_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("duplicate_matches_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("upload_ip", sa.String(length=45), nullable=True))
        batch_op.add_column(sa.Column("upload_user_agent", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("device_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("photo_hashes_json", sa.Text(), nullable=True))
        batch_op.create_index("ix_ilan_moderasyon_analiz_spam_score", ["spam_score"])
        batch_op.create_index("ix_ilan_moderasyon_analiz_duplicate_score", ["duplicate_score"])
        batch_op.create_index("ix_ilan_moderasyon_analiz_device_fingerprint", ["device_fingerprint"])


def downgrade():
    with op.batch_alter_table("ilan_moderasyon_analiz", schema=None) as batch_op:
        batch_op.drop_index("ix_ilan_moderasyon_analiz_device_fingerprint")
        batch_op.drop_index("ix_ilan_moderasyon_analiz_duplicate_score")
        batch_op.drop_index("ix_ilan_moderasyon_analiz_spam_score")
        batch_op.drop_column("photo_hashes_json")
        batch_op.drop_column("device_fingerprint")
        batch_op.drop_column("upload_user_agent")
        batch_op.drop_column("upload_ip")
        batch_op.drop_column("duplicate_matches_json")
        batch_op.drop_column("duplicate_reasons_json")
        batch_op.drop_column("spam_reasons_json")
        batch_op.drop_column("duplicate_score")
        batch_op.drop_column("spam_score")
