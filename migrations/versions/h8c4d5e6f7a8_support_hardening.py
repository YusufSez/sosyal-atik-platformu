"""Support hardening: private attachments, bildirim mesaj_id.

Revision ID: h8c4d5e6f7a8
Revises: g2b3c4d5e6f7
"""

import sqlalchemy as sa
from alembic import op


revision = "h8c4d5e6f7a8"
down_revision = "g2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("destek_talebi", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("ek_resim_orijinal", sa.String(length=255), nullable=True)
        )

    with op.batch_alter_table("bildirim", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mesaj_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_bildirim_mesaj_id",
            "mesaj",
            ["mesaj_id"],
            ["id"],
        )
        batch_op.create_index("ix_bildirim_mesaj_id", ["mesaj_id"], unique=False)

    op.create_index(
        "ix_bildirim_user_tur_okundu_mesaj",
        "bildirim",
        ["user_id", "tur", "okundu", "mesaj_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_bildirim_user_tur_okundu_mesaj", table_name="bildirim")
    with op.batch_alter_table("bildirim", schema=None) as batch_op:
        batch_op.drop_index("ix_bildirim_mesaj_id")
        batch_op.drop_constraint("fk_bildirim_mesaj_id", type_="foreignkey")
        batch_op.drop_column("mesaj_id")
    with op.batch_alter_table("destek_talebi", schema=None) as batch_op:
        batch_op.drop_column("ek_resim_orijinal")
