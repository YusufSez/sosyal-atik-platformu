from flask_login import UserMixin

from extensions import db
from utils import tr_time


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False)
    ad = db.Column(db.String(100), nullable=True)
    soyad = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    dogum_tarihi = db.Column(db.String(20))
    il = db.Column(db.String(100))
    ilce = db.Column(db.String(100))
    telefon = db.Column(db.String(20))
    adres = db.Column(db.String(255), nullable=True)
    profil_aciklama = db.Column(db.Text, nullable=True)
    telefon_verified = db.Column(db.Boolean, default=False, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    # Authorization role (kept in sync with `is_admin` for backward compatibility).
    # Values: user, admin, superadmin
    role = db.Column(db.String(20), nullable=False, default="user", index=True)
    # Ban state (superadmin can ban/unban users).
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    banned_at = db.Column(db.DateTime, nullable=True)
    ban_reason = db.Column(db.Text, nullable=True)
    ban_expires_at = db.Column(db.DateTime, nullable=True)
    banned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    is_deactivated = db.Column(db.Boolean, default=False, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    is_kurum = db.Column(db.Boolean, default=False)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    guven_puani = db.Column(db.Integer, default=0)
    xp = db.Column(db.Integer, default=0)
    profile_image = db.Column(db.String(60), nullable=True, default="default.jpg")
    kaynaklar = db.relationship("Kaynak", backref="sahip", lazy=True)
    atiklar = db.relationship("Atik", backref="sahip", lazy=True)
    banned_by = db.relationship(
        "User",
        foreign_keys=[banned_by_id],
        remote_side="User.id",
        backref=db.backref("banladigi_kullanicilar", lazy=True),
    )

    @property
    def display_name(self) -> str:
        parts = [p for p in (self.ad, self.soyad) if p]
        return " ".join(parts).strip() or self.username


class IlanResim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    dosya = db.Column(db.String(60), nullable=False)
    sira = db.Column(db.Integer, default=0)
    tarih = db.Column(db.DateTime, default=tr_time)
    kaynak = db.relationship(
        "Kaynak",
        backref=db.backref("fotograflar", lazy=True, order_by="IlanResim.sira"),
        foreign_keys=[kaynak_id],
    )
    atik = db.relationship(
        "Atik",
        backref=db.backref("fotograflar", lazy=True, order_by="IlanResim.sira"),
        foreign_keys=[atik_id],
    )


class Kaynak(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    baslik = db.Column(db.String(100), nullable=False)
    aciklama = db.Column(db.Text, nullable=False)
    durum = db.Column(db.String(50), nullable=False)
    kategori = db.Column(db.String(50), nullable=False)
    resim = db.Column(db.String(60), nullable=False, default="default.jpg")
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    ilan_durumu = db.Column(db.String(50), nullable=False, default="Aktif")
    moderation_status = db.Column(db.String(30), nullable=False, default="approved")
    moderation_reason = db.Column(db.Text, nullable=True)
    ai_risk_score = db.Column(db.Integer, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tarih = db.Column(db.DateTime, default=tr_time)


class Atik(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    baslik = db.Column(db.String(100), nullable=False)
    aciklama = db.Column(db.Text, nullable=False)
    resim = db.Column(db.String(60), nullable=True)
    latitude = db.Column(db.Float, default=41.015)
    longitude = db.Column(db.Float, default=28.979)
    kategori = db.Column(db.String(50), nullable=True)
    ilan_durumu = db.Column(db.String(50), nullable=False, default="Aktif")
    moderation_status = db.Column(db.String(30), nullable=False, default="approved")
    moderation_reason = db.Column(db.Text, nullable=True)
    ai_risk_score = db.Column(db.Integer, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tarih = db.Column(db.DateTime, default=tr_time)


class AtikMerkezi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ad = db.Column(db.String(150), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    adres = db.Column(db.String(255))


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=tr_time)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=True)
    user = db.relationship("User", backref="comments", lazy=True)
    kaynak = db.relationship("Kaynak", backref="comments", lazy=True)
    atik = db.relationship("Atik", backref="comments", lazy=True)
    replies = db.relationship(
        "Comment",
        backref=db.backref("parent", remote_side=[id]),
        lazy=True,
        order_by="Comment.timestamp.asc()",
    )


class Mesaj(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=tr_time)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    sender = db.relationship("User", foreign_keys=[sender_id], backref="gonderilen_mesajlar")
    receiver = db.relationship("User", foreign_keys=[receiver_id], backref="alinan_mesajlar")
    kaynak = db.relationship("Kaynak", backref="mesajlar", lazy=True)
    atik = db.relationship("Atik", backref="mesajlar", lazy=True)


class Favori(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    timestamp = db.Column(db.DateTime, default=tr_time)
    user = db.relationship("User", backref="favoriler", lazy=True)
    kaynak = db.relationship("Kaynak", backref="favoriler", lazy=True)
    atik = db.relationship("Atik", backref="favoriler", lazy=True)


class Goruntulenme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    timestamp = db.Column(db.DateTime, default=tr_time)
    kaynak = db.relationship("Kaynak", backref="goruntulenmeler", lazy=True)
    atik = db.relationship("Atik", backref="goruntulenmeler", lazy=True)
    user = db.relationship("User", backref="goruntulenmeler", lazy=True)


class Bildirim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    baslik = db.Column(db.String(200), nullable=False)
    icerik = db.Column(db.Text, nullable=False)
    tur = db.Column(db.String(50), nullable=False)
    okundu = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=tr_time)
    link = db.Column(db.String(200), nullable=True)
    mesaj_id = db.Column(db.Integer, db.ForeignKey("mesaj.id"), nullable=True, index=True)
    user = db.relationship("User", backref="bildirimler", lazy=True)
    mesaj = db.relationship("Mesaj", backref="bildirimler", lazy=True)


class Sikayet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    mesaj_id = db.Column(db.Integer, db.ForeignKey("mesaj.id"), nullable=True)
    tur = db.Column(db.String(20), nullable=True, index=True)
    sebep = db.Column(db.Text, nullable=False)
    aciklama = db.Column(db.Text, nullable=True)
    durum = db.Column(db.String(50), nullable=False, default="Bekliyor", index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    timestamp = db.Column(db.DateTime, default=tr_time, index=True)
    user = db.relationship("User", foreign_keys=[user_id], backref="sikayetler", lazy=True)
    reported_user = db.relationship("User", foreign_keys=[reported_user_id], backref="alinan_sikayetler", lazy=True)
    reviewer = db.relationship("User", foreign_keys=[reviewer_id], backref="incelenen_sikayetler", lazy=True)
    kaynak = db.relationship("Kaynak", backref="sikayetler", lazy=True)
    atik = db.relationship("Atik", backref="sikayetler", lazy=True)
    mesaj = db.relationship("Mesaj", backref="sikayetler", lazy=True)


class CevreselEtki(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    tur = db.Column(db.String(20), nullable=False)
    kategori = db.Column(db.String(50), nullable=False)
    co2e_kg = db.Column(db.Float, nullable=False, default=0)
    su_litre = db.Column(db.Float, nullable=False, default=0)
    atik_kg = db.Column(db.Float, nullable=False, default=0)
    dongusel_skor = db.Column(db.Integer, nullable=False, default=0)
    hesaplama_versiyonu = db.Column(db.String(10), default="1.0")
    timestamp = db.Column(db.DateTime, default=tr_time)
    user = db.relationship("User", backref="cevresel_etkiler", lazy=True)
    kaynak = db.relationship("Kaynak", backref="cevresel_etki", uselist=False, lazy=True)
    atik = db.relationship("Atik", backref="cevresel_etki", uselist=False, lazy=True)

    __table_args__ = (
        db.UniqueConstraint("kaynak_id", name="uq_etki_kaynak"),
        db.UniqueConstraint("atik_id", name="uq_etki_atik"),
    )


class KullaniciRozet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rozet_kod = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=tr_time)
    user = db.relationship("User", backref=db.backref("rozetler", lazy=True))

    __table_args__ = (
        db.UniqueConstraint("user_id", "rozet_kod", name="uq_kullanici_rozet"),
    )


class EmailToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)
    nonce = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=tr_time)
    user = db.relationship("User", backref=db.backref("email_tokens", lazy=True))

    __table_args__ = (
        db.Index("ix_email_token_nonce_purpose", "nonce", "purpose"),
    )


class IlanModerasyonAnaliz(db.Model):
    """Versiyonlu AI moderasyon analiz geçmişi."""

    __tablename__ = "ilan_moderasyon_analiz"

    id = db.Column(db.Integer, primary_key=True)
    tur = db.Column(db.String(10), nullable=False, index=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True, index=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True, index=True)
    analysis_version = db.Column(db.Integer, nullable=False, default=1)
    is_current = db.Column(db.Boolean, nullable=False, default=True, index=True)
    model_name = db.Column(db.String(80), nullable=False, default="gemini-2.5-flash")
    prompt_version = db.Column(db.String(20), nullable=False, default="2.1")
    initial_risk = db.Column(db.Integer, nullable=True)
    final_risk = db.Column(db.Integer, nullable=True)
    risk_adjustment = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String(80), nullable=True)
    purpose = db.Column(db.String(40), nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    is_recyclable = db.Column(db.Boolean, nullable=False, default=False)
    matched_rules_json = db.Column(db.Text, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    moderation_status = db.Column(db.String(30), nullable=False, default="approved")
    whitelist_applied = db.Column(db.Boolean, nullable=False, default=False)
    risk_adjustment_reason = db.Column(db.Text, nullable=True)
    text_analysis_json = db.Column(db.Text, nullable=True)
    vision_analysis_json = db.Column(db.Text, nullable=True)
    photo_analyses_json = db.Column(db.Text, nullable=True)
    raw_json = db.Column(db.Text, nullable=True)
    spam_score = db.Column(db.Integer, nullable=True, index=True)
    duplicate_score = db.Column(db.Integer, nullable=True, index=True)
    spam_reasons_json = db.Column(db.Text, nullable=True)
    duplicate_reasons_json = db.Column(db.Text, nullable=True)
    duplicate_matches_json = db.Column(db.Text, nullable=True)
    upload_ip = db.Column(db.String(45), nullable=True)
    upload_user_agent = db.Column(db.String(500), nullable=True)
    device_fingerprint = db.Column(db.String(64), nullable=True, index=True)
    photo_hashes_json = db.Column(db.Text, nullable=True)
    triggered_by = db.Column(db.String(30), nullable=False, default="upload")
    admin_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=tr_time, index=True)
    kaynak = db.relationship("Kaynak", backref=db.backref("moderasyon_analizleri", lazy=True))
    atik = db.relationship("Atik", backref=db.backref("moderasyon_analizleri", lazy=True))
    admin = db.relationship("User", foreign_keys=[admin_user_id])


class IlanModerasyonTimeline(db.Model):
    """Moderasyon olay akışı."""

    __tablename__ = "ilan_moderasyon_timeline"

    id = db.Column(db.Integer, primary_key=True)
    tur = db.Column(db.String(10), nullable=False, index=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True, index=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True, index=True)
    analiz_id = db.Column(db.Integer, db.ForeignKey("ilan_moderasyon_analiz.id"), nullable=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    detail_json = db.Column(db.Text, nullable=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=tr_time, index=True)
    analiz = db.relationship("IlanModerasyonAnaliz", backref=db.backref("timeline_events", lazy=True))
    admin = db.relationship("User", foreign_keys=[admin_user_id])


class IlanModerasyonNot(db.Model):
    """Admin moderasyon notları."""

    __tablename__ = "ilan_moderasyon_not"

    id = db.Column(db.Integer, primary_key=True)
    tur = db.Column(db.String(10), nullable=False, index=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True, index=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True, index=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=tr_time, index=True)
    admin = db.relationship("User", backref=db.backref("moderasyon_notlari", lazy=True))


class IlanModerasyonKarar(db.Model):
    """AI vs Admin karar karşılaştırması (Phase 1 analitik)."""

    __tablename__ = "ilan_moderasyon_karar"

    id = db.Column(db.Integer, primary_key=True)
    tur = db.Column(db.String(10), nullable=False, index=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True, index=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True, index=True)
    analiz_id = db.Column(db.Integer, db.ForeignKey("ilan_moderasyon_analiz.id"), nullable=True)
    action_type = db.Column(db.String(30), nullable=False, index=True)
    ai_decision = db.Column(db.String(30), nullable=False)
    admin_decision = db.Column(db.String(30), nullable=False)
    decision_match = db.Column(db.Boolean, nullable=False, default=False)
    override = db.Column(db.Boolean, nullable=False, default=False, index=True)
    decision_version = db.Column(db.Integer, nullable=True)
    decision_reason = db.Column(db.Text, nullable=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    decision_time = db.Column(db.DateTime, default=tr_time, index=True)
    category = db.Column(db.String(80), nullable=True)
    purpose = db.Column(db.String(40), nullable=True)
    analiz = db.relationship("IlanModerasyonAnaliz", backref=db.backref("kararlar", lazy=True))
    admin = db.relationship("User", foreign_keys=[admin_user_id])


class IlanModerasyonActivityLog(db.Model):
    """Moderasyon paneli admin activity log."""

    __tablename__ = "ilan_moderasyon_activity_log"

    id = db.Column(db.Integer, primary_key=True)
    tur = db.Column(db.String(10), nullable=True, index=True)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True, index=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True, index=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    note = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=tr_time, index=True)
    admin = db.relationship("User", backref=db.backref("moderasyon_activity_logs", lazy=True))


class AiModerasyonHealthLog(db.Model):
    """AI istek sağlık metrikleri (production monitoring)."""

    __tablename__ = "ai_moderasyon_health_log"

    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(80), nullable=False, index=True)
    prompt_version = db.Column(db.String(20), nullable=False)
    request_type = db.Column(db.String(30), nullable=False, default="vision")
    success = db.Column(db.Boolean, nullable=False, default=True, index=True)
    response_time_ms = db.Column(db.Integer, nullable=True)
    error_type = db.Column(db.String(30), nullable=True, index=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=tr_time, index=True)


class AdminAuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    target = db.Column(db.String(200))
    target_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    detail = db.Column(db.Text)
    reason = db.Column(db.Text, nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500), nullable=True)
    tarih = db.Column(db.DateTime, default=tr_time, index=True)
    admin = db.relationship("User", foreign_keys=[admin_id], backref=db.backref("admin_audit_logs", lazy=True))
    target_user = db.relationship("User", foreign_keys=[target_user_id], backref=db.backref("hedef_audit_logs", lazy=True))


class DestekTalebi(db.Model):
    __tablename__ = "destek_talebi"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    guest_name = db.Column(db.String(100), nullable=True)
    guest_surname = db.Column(db.String(100), nullable=True)
    guest_email = db.Column(db.String(150), nullable=True, index=True)
    guest_phone = db.Column(db.String(20), nullable=True)
    baslik = db.Column(db.String(200), nullable=False)
    kategori = db.Column(db.String(30), nullable=False, index=True)
    mesaj = db.Column(db.Text, nullable=False)
    ek_resim = db.Column(db.String(120), nullable=True)
    ek_resim_orijinal = db.Column(db.String(255), nullable=True)
    durum = db.Column(db.String(30), nullable=False, default="Bekliyor", index=True)
    admin_not = db.Column(db.Text, nullable=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=tr_time)
    updated_at = db.Column(db.DateTime, default=tr_time, onupdate=tr_time)
    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("destek_talepleri", lazy=True))
    reviewer = db.relationship("User", foreign_keys=[reviewer_id], backref=db.backref("incelenen_destekler", lazy=True))
    durum_gecmisi = db.relationship(
        "DestekDurumGecmisi",
        backref="talep",
        lazy=True,
        order_by="DestekDurumGecmisi.created_at",
    )

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    @property
    def kaynak_tipi(self) -> str:
        return "Misafir" if self.is_guest else "Kullanıcı"

    @property
    def gosterim_adi(self) -> str:
        if self.user:
            return self.user.display_name
        parts = [p for p in (self.guest_name, self.guest_surname) if p]
        return " ".join(parts).strip() or "—"

    @property
    def gosterim_email(self) -> str:
        if self.user:
            return self.user.email or "—"
        return self.guest_email or "—"

    @property
    def gosterim_telefon(self) -> str:
        if self.user:
            return self.user.telefon or "—"
        return self.guest_phone or "—"


class DestekDurumGecmisi(db.Model):
    __tablename__ = "destek_durum_gecmisi"

    id = db.Column(db.Integer, primary_key=True)
    talep_id = db.Column(db.Integer, db.ForeignKey("destek_talebi.id"), nullable=False, index=True)
    eski_durum = db.Column(db.String(30), nullable=True)
    yeni_durum = db.Column(db.String(30), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    not_metni = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=tr_time, index=True)
    admin = db.relationship("User", foreign_keys=[admin_id], backref=db.backref("destek_durum_loglari", lazy=True))
