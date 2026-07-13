from extensions import db


def ensure_schema():
    """Mevcut SQLite veritabanına yeni sütunları güvenli şekilde ekler."""
    from sqlalchemy import inspect, text

    if db.engine.dialect.name != "sqlite":
        return
    inspector = inspect(db.engine)
    if "user" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("user")}
        with db.engine.begin() as conn:
            if "latitude" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN latitude FLOAT"))
            if "longitude" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN longitude FLOAT"))
            if "is_admin" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
            if "guven_puani" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN guven_puani INTEGER DEFAULT 0"))
            if "is_kurum" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_kurum BOOLEAN DEFAULT 0"))
            if "xp" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN xp INTEGER DEFAULT 0"))
            # Production role + ban fields (SQLite only) for local compatibility
            if "role" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'user'"))
            if "is_banned" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_banned BOOLEAN DEFAULT 0"))
            if "banned_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN banned_at DATETIME"))
            if "ban_reason" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN ban_reason TEXT"))
            if "ban_expires_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN ban_expires_at DATETIME"))
            if "is_deactivated" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_deactivated BOOLEAN DEFAULT 0"))
            if "last_login_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN last_login_at DATETIME"))
            if "last_seen" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN last_seen DATETIME"))
            if "terms_accepted_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN terms_accepted_at DATETIME"))
            if "email_verified" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
                conn.execute(text("UPDATE user SET email_verified = 1"))
            if "email_verified_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN email_verified_at DATETIME"))
            if "ad" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN ad VARCHAR(100)"))
            if "soyad" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN soyad VARCHAR(100)"))
            if "adres" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN adres VARCHAR(255)"))
            if "profil_aciklama" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN profil_aciklama TEXT"))
            if "telefon_verified" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN telefon_verified BOOLEAN DEFAULT 0"))
            if "mahalle" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN mahalle VARCHAR(120)"))

    if "destek_talebi" in inspector.get_table_names():
        destek_cols = {c["name"] for c in inspector.get_columns("destek_talebi")}
        with db.engine.begin() as conn:
            for col, ddl in (
                ("guest_name", "VARCHAR(100)"),
                ("guest_surname", "VARCHAR(100)"),
                ("guest_email", "VARCHAR(150)"),
                ("guest_phone", "VARCHAR(20)"),
                ("ip_address", "VARCHAR(45)"),
                ("user_agent", "VARCHAR(500)"),
            ):
                if col not in destek_cols:
                    conn.execute(text(f"ALTER TABLE destek_talebi ADD COLUMN {col} {ddl}"))

    if "comment" in inspector.get_table_names():
        comment_cols = {c["name"] for c in inspector.get_columns("comment")}
        with db.engine.begin() as conn:
            if "atik_id" not in comment_cols:
                conn.execute(text("ALTER TABLE comment ADD COLUMN atik_id INTEGER"))
            if "parent_id" not in comment_cols:
                conn.execute(text("ALTER TABLE comment ADD COLUMN parent_id INTEGER"))

    for table in ("kaynak", "atik"):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        with db.engine.begin() as conn:
            if "ilan_durumu" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN ilan_durumu VARCHAR(50) DEFAULT 'Aktif'"))
            conn.execute(text(f"UPDATE {table} SET ilan_durumu = 'Aktif' WHERE ilan_durumu IS NULL"))
            if "moderation_status" not in cols:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN moderation_status VARCHAR(30) DEFAULT 'approved'")
                )
            if "moderation_reason" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN moderation_reason TEXT"))
            if "ai_risk_score" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN ai_risk_score INTEGER"))
            conn.execute(
                text(f"UPDATE {table} SET moderation_status = 'approved' WHERE moderation_status IS NULL")
            )

    if "sikayet" in inspector.get_table_names():
        sikayet_cols = {c["name"] for c in inspector.get_columns("sikayet")}
        with db.engine.begin() as conn:
            if "mesaj_id" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN mesaj_id INTEGER"))
            if "reported_user_id" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN reported_user_id INTEGER"))
            if "tur" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN tur VARCHAR(20)"))
            if "aciklama" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN aciklama TEXT"))
            if "reviewer_id" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN reviewer_id INTEGER"))
            if "reviewed_at" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN reviewed_at DATETIME"))

    if "admin_audit_log" in inspector.get_table_names():
        audit_cols = {c["name"] for c in inspector.get_columns("admin_audit_log")}
        with db.engine.begin() as conn:
            if "target_user_id" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN target_user_id INTEGER"))
            if "reason" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN reason TEXT"))
            if "old_value" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN old_value TEXT"))
            if "new_value" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN new_value TEXT"))
            if "user_agent" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN user_agent VARCHAR(500)"))
