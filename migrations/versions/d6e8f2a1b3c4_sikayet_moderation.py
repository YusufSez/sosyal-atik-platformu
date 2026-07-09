"""Şikayet moderasyonu, genişletilmiş audit log ve kullanıcı ban süresi.

Revision ID: d6e8f2a1b3c4
Revises: c5d1f3a7b9d2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "d6e8f2a1b3c4"
down_revision = "c5d1f3a7b9d2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("ban_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column(
                "is_deactivated",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            )
        )
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("sikayet") as batch:
        batch.add_column(sa.Column("reported_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("tur", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("aciklama", sa.Text(), nullable=True))
        batch.add_column(sa.Column("reviewer_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_sikayet_reported_user", "user", ["reported_user_id"], ["id"])
        batch.create_foreign_key("fk_sikayet_reviewer", "user", ["reviewer_id"], ["id"])

    with op.batch_alter_table("admin_audit_log") as batch:
        batch.add_column(sa.Column("target_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("old_value", sa.Text(), nullable=True))
        batch.add_column(sa.Column("new_value", sa.Text(), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(length=500), nullable=True))
        batch.create_foreign_key("fk_audit_target_user", "user", ["target_user_id"], ["id"])

    # Durum migrasyonu
    bind.execute(text("UPDATE sikayet SET durum = 'Bekliyor' WHERE durum = 'Beklemede'"))
    bind.execute(text("UPDATE sikayet SET durum = 'İşlem Yapıldı' WHERE durum = 'İncelendi'"))

    # Tür ve reported_user_id doldur
    rows = bind.execute(
        text(
            "SELECT id, user_id, kaynak_id, atik_id, mesaj_id, sebep FROM sikayet"
        )
    ).fetchall()
    for row in rows:
        sid, user_id, kaynak_id, atik_id, mesaj_id, sebep = row
        tur = None
        reported_user_id = None
        aciklama = None

        if mesaj_id:
            tur = "mesaj"
            msg = bind.execute(
                text("SELECT sender_id, receiver_id FROM mesaj WHERE id = :id"),
                {"id": mesaj_id},
            ).fetchone()
            if msg:
                sender_id, receiver_id = msg
                reported_user_id = sender_id if sender_id != user_id else receiver_id
        elif kaynak_id:
            tur = "kaynak"
            owner = bind.execute(
                text("SELECT user_id FROM kaynak WHERE id = :id"),
                {"id": kaynak_id},
            ).fetchone()
            if owner:
                reported_user_id = owner[0]
        elif atik_id:
            tur = "atik"
            owner = bind.execute(
                text("SELECT user_id FROM atik WHERE id = :id"),
                {"id": atik_id},
            ).fetchone()
            if owner:
                reported_user_id = owner[0]

        if sebep and "| Açıklama:" in sebep:
            parts = sebep.split("| Açıklama:", 1)
            aciklama = parts[1].strip()[:2000] if len(parts) > 1 else None

        bind.execute(
            text(
                "UPDATE sikayet SET tur = :tur, reported_user_id = :ruid, aciklama = :aciklama WHERE id = :id"
            ),
            {"tur": tur, "ruid": reported_user_id, "aciklama": aciklama, "id": sid},
        )

    op.create_index("ix_sikayet_durum", "sikayet", ["durum"], unique=False)
    op.create_index("ix_sikayet_tur", "sikayet", ["tur"], unique=False)
    op.create_index("ix_sikayet_timestamp", "sikayet", ["timestamp"], unique=False)


def downgrade():
    op.drop_index("ix_sikayet_timestamp", table_name="sikayet")
    op.drop_index("ix_sikayet_tur", table_name="sikayet")
    op.drop_index("ix_sikayet_durum", table_name="sikayet")

    with op.batch_alter_table("admin_audit_log") as batch:
        batch.drop_constraint("fk_audit_target_user", type_="foreignkey")
        batch.drop_column("user_agent")
        batch.drop_column("new_value")
        batch.drop_column("old_value")
        batch.drop_column("reason")
        batch.drop_column("target_user_id")

    with op.batch_alter_table("sikayet") as batch:
        batch.drop_constraint("fk_sikayet_reviewer", type_="foreignkey")
        batch.drop_constraint("fk_sikayet_reported_user", type_="foreignkey")
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewer_id")
        batch.drop_column("aciklama")
        batch.drop_column("tur")
        batch.drop_column("reported_user_id")

    with op.batch_alter_table("user") as batch:
        batch.drop_column("last_login_at")
        batch.drop_column("is_deactivated")
        batch.drop_column("ban_expires_at")

    bind = op.get_bind()
    bind.execute(text("UPDATE sikayet SET durum = 'Beklemede' WHERE durum = 'Bekliyor'"))
    bind.execute(text("UPDATE sikayet SET durum = 'İncelendi' WHERE durum = 'İşlem Yapıldı'"))
