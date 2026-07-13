"""Uygulama genelinde kullanılan sabitler."""

# RBAC rolleri (User.role)
ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_SUPERADMIN = "superadmin"
ROLE_MUNICIPALITY = "municipality"
ROLE_MINISTRY = "ministry"
ROLE_COMPANY = "company"
ROLE_INSTITUTION = "institution"

MARKETPLACE_ROLES = (ROLE_COMPANY, ROLE_INSTITUTION)

# Kurumsal kaynak pazarı durumları
MP_LISTING_YAYINDA = "yayinda"
MP_LISTING_REZERVE = "rezerve"
MP_LISTING_ANLASILDI = "anlasildi"
MP_LISTING_TESLIM = "teslim"
MP_LISTING_IPTAL = "iptal"
MP_LISTING_STATUSES = (
    MP_LISTING_YAYINDA,
    MP_LISTING_REZERVE,
    MP_LISTING_ANLASILDI,
    MP_LISTING_TESLIM,
    MP_LISTING_IPTAL,
)

MP_OFFER_BEKLIYOR = "bekliyor"
MP_OFFER_KABUL = "kabul"
MP_OFFER_RED = "red"
MP_OFFER_IPTAL = "iptal"
MP_OFFER_STATUSES = (
    MP_OFFER_BEKLIYOR,
    MP_OFFER_KABUL,
    MP_OFFER_RED,
    MP_OFFER_IPTAL,
)

MP_KATEGORILER = (
    "Hammadde",
    "Ambalaj",
    "Elektronik",
    "Mobilya",
    "Tekstil",
    "Gıda Yan Ürün",
    "Lojistik Kapasite",
    "Diğer",
)

MP_NEARBY_RADIUS_KM = 50

# Sustainability Scoring Engine (100 puan)
SUSTAINABILITY_WEIGHTS = {
    "geri_donusum": 18,
    "teslim": 18,
    "katilim": 14,
    "kaynak_paylasimi": 14,
    "karbon": 14,
    "teslim_suresi": 12,
    "ai_dogruluk": 10,
}
SUSTAINABILITY_CRITERION_LABELS = {
    "geri_donusum": "Geri dönüşüm oranı",
    "teslim": "Teslim oranı",
    "katilim": "Vatandaş katılımı",
    "kaynak_paylasimi": "Kaynak paylaşımı",
    "karbon": "Karbon azaltımı",
    "teslim_suresi": "Teslim süresi",
    "ai_dogruluk": "AI doğruluk oranı",
}
# Harf notu eşikleri (puan alt sınırı) — 11 ile 31 aynı banda düşmesin
SUSTAINABILITY_GRADES = (
    (95, "A+"),
    (90, "A"),
    (80, "B+"),
    (70, "B"),
    (60, "C+"),
    (50, "C"),
    (40, "D+"),
    (30, "D"),
    (20, "E"),
    (0, "F"),
)
# Eksik veri (payda=0) için nötr skor — sıfırlar toplamı ezmesin
SUSTAINABILITY_MISSING_NEUTRAL = 45.0
# Karbon: bölge başına bu kg CO₂e tasarrufu ≈ 100 puan (log ölçek)
SUSTAINABILITY_CO2_BENCHMARK_KG = 50.0
# Teslim süresi: ideal gün / sıfır puan gün
SUSTAINABILITY_DELIVERY_IDEAL_DAYS = 3.0
SUSTAINABILITY_DELIVERY_MAX_DAYS = 30.0

# CO₂e → tahmini enerji tasarrufu (kWh). TR şebeke yoğunluğu ~0.4 kg CO₂e/kWh.
CO2E_KG_PER_KWH = 0.4

# Belediye kategori analizi paneli (görüntüleme grupları)
MUNICIPALITY_CATEGORY_GROUPS = (
    "Plastik",
    "Cam",
    "Metal",
    "Elektronik",
    "Organik",
    "Bitkisel Yağ",
    "Diğer",
)

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
ADMIN_USERS_PER_PAGE = 50
ADMIN_DESTEK_PER_PAGE = 50
MODERATION_LISTE_BRANCH_LIMIT = 500

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

DESTEK_KATEGORI_BAN_ITIRAZI = "BAN_ITIRAZI"  # Eski kayıtlar için geriye dönük
DESTEK_KATEGORI_BAN_ITIRAZI_LABEL = "Ban İtirazı"
DESTEK_KATEGORILERI = (
    "Öneri",
    "İstek",
    "Şikayet",
    "Hata Bildirimi",
    DESTEK_KATEGORI_BAN_ITIRAZI_LABEL,
)
DESTEK_DURUMLARI = ("Bekliyor", "İnceleniyor", "Yanıtlandı", "Kapatıldı")
RATE_BAN_ITIRAZ = "5 per hour"
RATE_DESTEK_GUEST = "5 per hour"
RATE_DESTEK_AUTH = "10 per hour"

# Eski durumlar → yeni (migration + runtime)
SIKAYET_DURUM_LEGACY_MAP = {
    "Beklemede": "Bekliyor",
    "İncelendi": "İşlem Yapıldı",
}
MAX_ILAN_FOTOSU = 10
MAX_SINGLE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000  # ~25 MP — decompression bomb koruması
MAX_UPLOAD_BYTES = MAX_SINGLE_IMAGE_BYTES * MAX_ILAN_FOTOSU

# Rate limiting (Flask-Limiter)
RATE_LOGIN = "5 per minute"
RATE_REGISTER = "3 per minute"
RATE_PASSWORD_RESET = "3 per hour"
RATE_EMAIL_RESEND = "3 per hour"
RATE_ILAN_CREATE = "20 per hour"
RATE_MESSAGE = "30 per minute"
RATE_MESSAGE_FETCH = "60 per minute"
RATE_SOCKET_TYPING_PER_SEC = 10
RATE_SOCKET_MESSAGE_PER_SEC = 5
RATE_SOCKET_SYNC_STATE_PER_SEC = 5
MESSAGE_PAGE_SIZE = 50
RATE_COMMENT = "15 per minute"
RATE_AI_ANALIZ = "10 per minute"
RATE_PUBLIC_API = "120 per minute"

EMAIL_VERIFY_REQUIRED_MSG = (
    "Bu işlemi yapabilmek için e-posta adresinizi doğrulamanız gerekiyor."
)

AI_RISK_AUTO_APPROVE_MAX = 30
AI_RISK_ADMIN_NOTIFY_MIN = 31
AI_RISK_REVIEW_MIN = 70
AI_RISK_REJECT_MIN = 90
# Geriye dönük uyumluluk — eski kod risk_skoru < 70 güvenli sayıyordu
AI_RISK_BLOCK_THRESHOLD = AI_RISK_REJECT_MIN
MESSAGE_AI_BLOCK_THRESHOLD = 55

AI_PROMPT_VERSION = "2.1"
AI_MODERATION_MODEL_DEFAULT = "gemini-2.5-flash"

MODERATION_STATUS_APPROVED = "approved"
MODERATION_STATUS_PENDING_REVIEW = "pending_review"
MODERATION_STATUS_REJECTED = "rejected"
MODERATION_STATUSES = (
    MODERATION_STATUS_APPROVED,
    MODERATION_STATUS_PENDING_REVIEW,
    MODERATION_STATUS_REJECTED,
)

# Phase 2 — Spam & Duplicate
SPAM_SHORT_DESC_MIN_LEN = 15
SPAM_FAST_CREATE_MINUTES = 5
SPAM_LOOKBACK_HOURS = 24
SPAM_DEVICE_LOOKBACK_DAYS = 7
DUPLICATE_LOOKBACK_DAYS = 30
DUPLICATE_MATCH_THRESHOLD = 40
DUPLICATE_HIGH_THRESHOLD = 70
DUPLICATE_MAX_CANDIDATES = 100
DUPLICATE_LOCATION_EPSILON = 0.002

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
