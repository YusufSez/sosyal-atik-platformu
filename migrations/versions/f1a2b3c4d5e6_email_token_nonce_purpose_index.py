"""Email token lookup index.

Revision ID: f1a2b3c4d5e6
Revises: e4a1b8c2d5f6
"""

from alembic import op


revision = "f1a2b3c4d5e6"
down_revision = "e4a1b8c2d5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_email_token_nonce_purpose",
        "email_token",
        ["nonce", "purpose"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_email_token_nonce_purpose", table_name="email_token")
