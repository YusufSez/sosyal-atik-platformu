"""UX Phase 1: banlayan admin + destek talepleri.

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""

import sqlalchemy as sa
from alembic import op


revision = "g2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("banned_by_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_banned_by_id",
            "user",
            ["banned_by_id"],
            ["id"],
        )
        batch_op.create_index("ix_user_banned_by_id", ["banned_by_id"], unique=False)

    op.create_table(
        "destek_talebi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("baslik", sa.String(length=200), nullable=False),
        sa.Column("kategori", sa.String(length=30), nullable=False),
        sa.Column("mesaj", sa.Text(), nullable=False),
        sa.Column("ek_resim", sa.String(length=120), nullable=True),
        sa.Column("durum", sa.String(length=30), nullable=False, server_default="Bekliyor"),
        sa.Column("admin_not", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["reviewer_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_destek_talebi_user_id", "destek_talebi", ["user_id"], unique=False)
    op.create_index("ix_destek_talebi_durum", "destek_talebi", ["durum"], unique=False)
    op.create_index("ix_destek_talebi_kategori", "destek_talebi", ["kategori"], unique=False)


def downgrade():
    op.drop_index("ix_destek_talebi_kategori", table_name="destek_talebi")
    op.drop_index("ix_destek_talebi_durum", table_name="destek_talebi")
    op.drop_index("ix_destek_talebi_user_id", table_name="destek_talebi")
    op.drop_table("destek_talebi")
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_index("ix_user_banned_by_id")
        batch_op.drop_constraint("fk_user_banned_by_id", type_="foreignkey")
        batch_op.drop_column("banned_by_id")
