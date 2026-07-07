from flask_login import UserMixin

from extensions import db
from utils import tr_time


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    dogum_tarihi = db.Column(db.String(20))
    il = db.Column(db.String(100))
    ilce = db.Column(db.String(100))
    telefon = db.Column(db.String(20))
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_kurum = db.Column(db.Boolean, default=False)
    guven_puani = db.Column(db.Integer, default=0)
    xp = db.Column(db.Integer, default=0)
    profile_image = db.Column(db.String(60), nullable=True, default="default.jpg")
    kaynaklar = db.relationship("Kaynak", backref="sahip", lazy=True)
    atiklar = db.relationship("Atik", backref="sahip", lazy=True)


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
    user = db.relationship("User", backref="comments", lazy=True)
    kaynak = db.relationship("Kaynak", backref="comments", lazy=True)
    atik = db.relationship("Atik", backref="comments", lazy=True)


class Mesaj(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=tr_time)
    is_read = db.Column(db.Boolean, default=False)
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
    user = db.relationship("User", backref="bildirimler", lazy=True)


class Sikayet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    sebep = db.Column(db.Text, nullable=False)
    durum = db.Column(db.String(50), nullable=False, default="Beklemede")
    timestamp = db.Column(db.DateTime, default=tr_time)
    user = db.relationship("User", backref="sikayetler", lazy=True)
    kaynak = db.relationship("Kaynak", backref="sikayetler", lazy=True)
    atik = db.relationship("Atik", backref="sikayetler", lazy=True)


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
