"""Role tabanlı yetki ve kullanıcı ban alanları.

Kullanıcı rollerini: user, admin, superadmin.
- SUPERADMIN_EMAIL ile eşleşen kullanıcı: superadmin
- Mevcut is_admin=True olanlar: admin (superadmin hariç)
"""

from alembic import op
import os

import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "c5d1f3a7b9d2"
down_revision = "b7e2a1c9d4f0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # role + ban alanları
    with op.batch_alter_table("user") as batch:
        batch.add_column(
            sa.Column(
                "role",
                sa.String(length=20),
                server_default="user",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "is_banned",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            )
        )
        batch.add_column(sa.Column("banned_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("ban_reason", sa.Text(), nullable=True))

    # Mevcut kullanıcıları role'a map et
    super_email = os.getenv("SUPERADMIN_EMAIL", "").strip().lower()
    if not super_email:
        super_email = os.getenv("ADMIN_EMAIL", "").strip().lower()

    if super_email:
        bind.execute(
            text(
                'UPDATE "user" SET role=:role, is_admin=true WHERE lower(email)=:email'
            ),
            {"role": "superadmin", "email": super_email},
        )
        bind.execute(
            text(
                'UPDATE "user" SET role=:role, is_admin=true WHERE is_admin=true AND lower(email)<>:email'
            ),
            {"role": "admin", "email": super_email},
        )
    else:
        # Env tanımlı değilse: geriye uyumluluk için ilk admin'i superadmin yap.
        row = bind.execute(
            text('SELECT id FROM "user" WHERE is_admin=true ORDER BY id ASC LIMIT 1')
        ).fetchone()
        if row:
            super_id = row[0]
            bind.execute(
                text('UPDATE "user" SET role=:role, is_admin=true WHERE id=:id'),
                {"role": "superadmin", "id": super_id},
            )
            bind.execute(
                text('UPDATE "user" SET role=:role, is_admin=true WHERE is_admin=true AND id<>:id'),
                {"role": "admin", "id": super_id},
            )

    # Garantile: is_admin=False ise role=user
    bind.execute(text('UPDATE "user" SET role=:role WHERE is_admin=false'), {"role": "user"})


def downgrade():
    with op.batch_alter_table("user") as batch:
        batch.drop_column("ban_reason")
        batch.drop_column("banned_at")
        batch.drop_column("is_banned")
        batch.drop_column("role")

