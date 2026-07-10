"""UX Phase 3 — misafir destek ve superadmin kullanıcı düzenleme.

Revision ID: j0e6f7a8b9c1
Revises: i9d5e6f7a8b0
"""

import sqlalchemy as sa
from alembic import op


revision = "j0e6f7a8b9c1"
down_revision = "i9d5e6f7a8b0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("adres", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("profil_aciklama", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("telefon_verified", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    with op.batch_alter_table("destek_talebi", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("guest_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("guest_surname", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("guest_email", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("guest_phone", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("ip_address", sa.String(length=45), nullable=True))
        batch_op.add_column(sa.Column("user_agent", sa.String(length=500), nullable=True))
        batch_op.create_index("ix_destek_talebi_guest_email", ["guest_email"], unique=False)

    op.create_table(
        "destek_durum_gecmisi",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("talep_id", sa.Integer(), nullable=False),
        sa.Column("eski_durum", sa.String(length=30), nullable=True),
        sa.Column("yeni_durum", sa.String(length=30), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column("not_metni", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["talep_id"], ["destek_talebi.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("destek_durum_gecmisi", schema=None) as batch_op:
        batch_op.create_index("ix_destek_durum_gecmisi_talep_id", ["talep_id"], unique=False)
        batch_op.create_index("ix_destek_durum_gecmisi_created_at", ["created_at"], unique=False)


def downgrade():
    op.drop_table("destek_durum_gecmisi")

    with op.batch_alter_table("destek_talebi", schema=None) as batch_op:
        batch_op.drop_index("ix_destek_talebi_guest_email")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("ip_address")
        batch_op.drop_column("guest_phone")
        batch_op.drop_column("guest_email")
        batch_op.drop_column("guest_surname")
        batch_op.drop_column("guest_name")
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("telefon_verified")
        batch_op.drop_column("profil_aciklama")
        batch_op.drop_column("adres")
