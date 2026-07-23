"""Postgres şema boşluğu: eksik kolonları güvenli şekilde ekle.

Bu veritabanında alembic_version boşken tablolar kısmen mevcuttu;
klasik `flask db upgrade` baştan create_table deneyeceği için başarısız olur.
Bu migration inspector ile yalnızca EKSİK kolon/tabloları ekler; veri silmez.

Revision ID: p6f3a4b5c6d7
Revises: o5e2f3a4b5c6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text


revision = "p6f3a4b5c6d7"
down_revision = "o5e2f3a4b5c6"
branch_labels = None
depends_on = None


def _cols(bind, table: str) -> set[str]:
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if column.name in _cols(bind, table):
        return
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.add_column(column)


def _create_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    existing = {ix["name"] for ix in inspector.get_indexes(table)}
    if name in existing:
        return
    op.create_index(name, table, columns, unique=False)


def upgrade():
    bind = op.get_bind()

    # --- user ---
    _add_column_if_missing(
        "user", sa.Column("role", sa.String(length=20), nullable=False, server_default="user")
    )
    _add_column_if_missing(
        "user", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    _add_column_if_missing("user", sa.Column("banned_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("user", sa.Column("ban_reason", sa.Text(), nullable=True))
    _add_column_if_missing("user", sa.Column("ban_expires_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(
        "user",
        sa.Column("is_deactivated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _add_column_if_missing("user", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("user", sa.Column("last_seen", sa.DateTime(), nullable=True))
    _add_column_if_missing("user", sa.Column("banned_by_id", sa.Integer(), nullable=True))
    _add_column_if_missing("user", sa.Column("ad", sa.String(length=100), nullable=True))
    _add_column_if_missing("user", sa.Column("soyad", sa.String(length=100), nullable=True))
    _add_column_if_missing("user", sa.Column("adres", sa.String(length=255), nullable=True))
    _add_column_if_missing("user", sa.Column("profil_aciklama", sa.Text(), nullable=True))
    _add_column_if_missing(
        "user",
        sa.Column("telefon_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _add_column_if_missing("user", sa.Column("mahalle", sa.String(length=120), nullable=True))

    if "banned_by_id" in _cols(bind, "user"):
        inspector = inspect(bind)
        fks = {fk.get("name") for fk in inspector.get_foreign_keys("user")}
        if "fk_user_banned_by_id" not in fks:
            with op.batch_alter_table("user", schema=None) as batch_op:
                batch_op.create_foreign_key(
                    "fk_user_banned_by_id", "user", ["banned_by_id"], ["id"]
                )
        _create_index_if_missing("user", "ix_user_banned_by_id", ["banned_by_id"])
        _create_index_if_missing("user", "ix_user_role", ["role"])

    if "role" in _cols(bind, "user") and "is_admin" in _cols(bind, "user"):
        bind.execute(
            text(
                'UPDATE "user" SET role = \'admin\' '
                "WHERE is_admin IS true AND (role IS NULL OR role = 'user')"
            )
        )
        bind.execute(
            text(
                'UPDATE "user" SET role = \'user\' '
                "WHERE (is_admin IS NOT true) AND (role IS NULL OR role = '')"
            )
        )

    # --- kaynak / atik moderation ---
    for table in ("kaynak", "atik"):
        _add_column_if_missing(
            table,
            sa.Column(
                "moderation_status",
                sa.String(length=30),
                nullable=False,
                server_default="approved",
            ),
        )
        _add_column_if_missing(table, sa.Column("moderation_reason", sa.Text(), nullable=True))
        _add_column_if_missing(table, sa.Column("ai_risk_score", sa.Integer(), nullable=True))

    # --- mesaj ---
    _add_column_if_missing("mesaj", sa.Column("read_at", sa.DateTime(), nullable=True))

    # --- bildirim ---
    _add_column_if_missing("bildirim", sa.Column("mesaj_id", sa.Integer(), nullable=True))

    # --- sikayet ---
    _add_column_if_missing("sikayet", sa.Column("reported_user_id", sa.Integer(), nullable=True))
    _add_column_if_missing("sikayet", sa.Column("tur", sa.String(length=20), nullable=True))
    _add_column_if_missing("sikayet", sa.Column("aciklama", sa.Text(), nullable=True))
    _add_column_if_missing("sikayet", sa.Column("reviewer_id", sa.Integer(), nullable=True))
    _add_column_if_missing("sikayet", sa.Column("reviewed_at", sa.DateTime(), nullable=True))

    # --- admin_audit_log ---
    _add_column_if_missing("admin_audit_log", sa.Column("target_user_id", sa.Integer(), nullable=True))
    _add_column_if_missing("admin_audit_log", sa.Column("reason", sa.Text(), nullable=True))
    _add_column_if_missing("admin_audit_log", sa.Column("old_value", sa.Text(), nullable=True))
    _add_column_if_missing("admin_audit_log", sa.Column("new_value", sa.Text(), nullable=True))
    _add_column_if_missing(
        "admin_audit_log", sa.Column("user_agent", sa.String(length=500), nullable=True)
    )

    # --- municipal_waste_centers ---
    inspector = inspect(bind)
    if "municipal_waste_centers" not in inspector.get_table_names():
        op.create_table(
            "municipal_waste_centers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("facility_type", sa.String(length=120), nullable=True),
            sa.Column("address", sa.String(length=255), nullable=True),
            sa.Column("district", sa.String(length=100), nullable=True),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("image_url", sa.String(length=500), nullable=True),
            sa.Column("waste_types", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("source_name", sa.String(length=150), nullable=False),
            sa.Column("external_key", sa.String(length=120), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_key", name="uq_mwc_source_external_key"),
        )
        op.create_index("ix_municipal_waste_centers_city", "municipal_waste_centers", ["city"])
        op.create_index("ix_municipal_waste_centers_source", "municipal_waste_centers", ["source"])
        op.create_index("ix_mwc_source_city", "municipal_waste_centers", ["source", "city"])
        op.create_index("ix_mwc_coords", "municipal_waste_centers", ["latitude", "longitude"])
        op.create_index(
            "ix_municipal_waste_centers_last_seen_at", "municipal_waste_centers", ["last_seen_at"]
        )
    else:
        _add_column_if_missing(
            "municipal_waste_centers", sa.Column("last_seen_at", sa.DateTime(), nullable=True)
        )



def downgrade():
    # Veri koruma: downgrade kolon düşürmez (geri alınamaz risk).
    pass
