"""Uygulama genelinde kullanılan sabitler."""

KATEGORILER_KAYNAK = [
    "Mobilya",
    "Elektronik",
    "Giysi",
    "Kitap",
    "Spor",
    "Oyun",
    "Mutfak",
    "Bahçe",
    "Beyaz Eşya",
    "Diğer",
]

KATEGORILER_ATIK = [
    "Plastik",
    "Kağıt",
    "Cam",
    "Metal",
    "Elektronik Atık",
    "Ahşap",
    "Tekstil",
    "Pil ve Akü",
    "Organik Atık",
    "Diğer",
]

DURUMLAR_KAYNAK = ["Temiz", "Kullanılmış", "Hasarlı"]

ILAN_DURUMLARI = ["Aktif", "Rezerve", "Teslim Edildi"]

DEFAULT_LAT = 41.015137
DEFAULT_LNG = 28.979530

ALLOWED_IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})
BLOCKED_UPLOAD_EXTENSIONS = frozenset({
    "exe", "php", "js", "svg", "html", "htm", "sh", "bat", "cmd", "py", "phtml",
})
ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
EXTENSION_TO_PIL_FORMAT = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
}
PIL_FORMAT_TO_EXT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}
PIL_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
ITEMS_PER_PAGE = 12
ADMIN_REPORTS_PER_PAGE = 25
ADMIN_LOGS_PER_PAGE = 50

# Şikayet durumları
SIKAYET_DURUMLARI = (
    "Bekliyor",
    "İnceleniyor",
    "İşlem Yapıldı",
    "Reddedildi",
    "Kapatıldı",
)

SIKAYET_TURLERI = ("mesaj", "kaynak", "atik")

# Ban süreleri (gün); None = süresiz
BAN_DURATION_OPTIONS = {
    "permanent": None,
    "1": 1,
    "3": 3,
    "7": 7,
    "30": 30,
    "90": 90,
}

# Eski durumlar → yeni (migration + runtime)
SIKAYET_DURUM_LEGACY_MAP = {
    "Beklemede": "Bekliyor",
    "İncelendi": "İşlem Yapıldı",
}
MAX_ILAN_FOTOSU = 10
MAX_SINGLE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = MAX_SINGLE_IMAGE_BYTES * MAX_ILAN_FOTOSU

# Rate limiting (Flask-Limiter)
RATE_LOGIN = "5 per minute"
RATE_REGISTER = "3 per minute"
RATE_PASSWORD_RESET = "3 per hour"
RATE_EMAIL_RESEND = "3 per hour"
RATE_ILAN_CREATE = "20 per hour"
RATE_MESSAGE = "30 per minute"
RATE_COMMENT = "15 per minute"
RATE_AI_ANALIZ = "10 per minute"
RATE_PUBLIC_API = "120 per minute"

EMAIL_VERIFY_REQUIRED_MSG = (
    "Bu işlemi yapabilmek için e-posta adresinizi doğrulamanız gerekiyor."
)

AI_RISK_BLOCK_THRESHOLD = 70
MESSAGE_AI_BLOCK_THRESHOLD = 55

HESAPLAMA_VERSIYONU = "1.0"

ETKI_KATSAYILARI_KAYNAK = {
    "Mobilya": {"co2e_kg": 45, "su_litre": 800},
    "Elektronik": {"co2e_kg": 35, "su_litre": 400},
    "Giysi": {"co2e_kg": 12, "su_litre": 2500},
    "Kitap": {"co2e_kg": 2, "su_litre": 50},
    "Spor": {"co2e_kg": 8, "su_litre": 150},
    "Oyun": {"co2e_kg": 5, "su_litre": 100},
    "Mutfak": {"co2e_kg": 15, "su_litre": 300},
    "Bahçe": {"co2e_kg": 10, "su_litre": 200},
    "Beyaz Eşya": {"co2e_kg": 80, "su_litre": 1200},
    "Diğer": {"co2e_kg": 10, "su_litre": 200},
}

ETKI_KATSAYILARI_ATIK = {
    "Plastik": {"co2e_kg": 3, "atik_kg": 2},
    "Kağıt": {"co2e_kg": 2, "atik_kg": 5},
    "Cam": {"co2e_kg": 0.5, "atik_kg": 8},
    "Metal": {"co2e_kg": 5, "atik_kg": 3},
    "Elektronik Atık": {"co2e_kg": 15, "atik_kg": 4},
    "Ahşap": {"co2e_kg": 2, "atik_kg": 6},
    "Tekstil": {"co2e_kg": 4, "atik_kg": 2},
    "Pil ve Akü": {"co2e_kg": 8, "atik_kg": 1},
    "Organik Atık": {"co2e_kg": 1, "atik_kg": 3},
    "Diğer": {"co2e_kg": 1, "atik_kg": 1},
}

# Oyunlaştırma
XP_ILAN_OLUSTUR = 25
XP_TESLIM = 50
XP_FAVORI = 5

SEVIYE_ESIKLERI = [0, 50, 150, 350, 700, 1200, 2000]
SEVIYE_ADLARI = [
    "Yeni Üye",
    "Paylaşımcı",
    "Yeşil El",
    "Sürdürülebilirlik Elçisi",
    "Eko Lider",
    "AtıkPort Ustası",
    "Efsane",
]

ROZET_TANIMLARI = {
    "ilk_ilan": {
        "ad": "İlk Adım",
        "aciklama": "İlk ilanını paylaştın",
        "ikon": "bi-flag-fill",
        "renk": "primary",
    },
    "ilk_teslim": {
        "ad": "Döngü Başladı",
        "aciklama": "İlk teslimini tamamladın",
        "ikon": "bi-recycle",
        "renk": "success",
    },
    "teslim_3": {
        "ad": "Üçlü Çember",
        "aciklama": "3 teslim tamamladın",
        "ikon": "bi-award",
        "renk": "info",
    },
    "teslim_10": {
        "ad": "On Numara",
        "aciklama": "10 teslim tamamladın",
        "ikon": "bi-trophy-fill",
        "renk": "warning",
    },
    "guven_5": {
        "ad": "Güvenilir Paylaşımcı",
        "aciklama": "Güven puanın 5'e ulaştı",
        "ikon": "bi-shield-check",
        "renk": "success",
    },
    "cevresel_sampiyon": {
        "ad": "Çevre Şampiyonu",
        "aciklama": "50 kg CO₂e üzeri tasarruf sağladın",
        "ikon": "bi-globe-americas",
        "renk": "success",
    },
    "favori_meraklisi": {
        "ad": "Keşifçi",
        "aciklama": "5 favori ilan ekledin",
        "ikon": "bi-heart-fill",
        "renk": "danger",
    },
}
