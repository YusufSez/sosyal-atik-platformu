from constants import AI_RISK_REJECT_MIN, MODERATION_STATUS_PENDING_REVIEW, MODERATION_STATUS_REJECTED
from helpers import _atik_moderasyon_duzelt, _atik_baglami_var
from services.ai_moderation import (
    apply_recyclable_adjustment,
    detect_recycling_purpose,
    detect_waste_material_mention,
    moderation_decision,
    normalize_ai_ilan_response,
    qualifies_for_risk_adjustment,
    resolve_moderation_status,
)
from services.ilan_moderation import moderasyon_reddedildi


def test_atik_baglami_pil_kategori():
    assert _atik_baglami_var(kategori_secim="Pil ve Akü") is True


def test_atik_baglami_baslik_anahtar_kelime():
    assert _atik_baglami_var(baslik="Eski piller", aciklama="") is True


def test_atik_baglami_yok():
    assert _atik_baglami_var(baslik="Masa lambası", aciklama="Temiz ürün") is False


def test_atik_moderasyon_duzelt_pil_foto():
    sonuc = {
        "kategori": "Pil ve Akü",
        "risk_skoru": 75,
        "guvenli": False,
    }
    duzeltilmis = _atik_moderasyon_duzelt(
        sonuc,
        baslik="Kullanılmış piller",
        kategori_secim="Pil ve Akü",
    )
    assert duzeltilmis["risk_skoru"] == 30
    assert duzeltilmis["guvenli"] is True
    assert duzeltilmis["risk_skoru"] < AI_RISK_REJECT_MIN


def test_atik_moderasyon_duzelt_dusuk_risk_dokunmaz():
    sonuc = {"kategori": "Plastik", "risk_skoru": 20, "guvenli": True}
    duzeltilmis = _atik_moderasyon_duzelt(sonuc, kategori_secim="Plastik")
    assert duzeltilmis["risk_skoru"] == 20


def test_atik_moderasyon_duzelt_kaynak_baglami_yok():
    sonuc = {"kategori": "Diğer", "risk_skoru": 75, "guvenli": True}
    duzeltilmis = _atik_moderasyon_duzelt(sonuc, baslik="Antika vazo")
    assert duzeltilmis["risk_skoru"] == 75
    assert duzeltilmis["guvenli"] is True


def test_bitkisel_atik_yag_whitelist():
    sonuc = {
        "kategori": "Diğer",
        "risk_skoru": 80,
        "guvenli": False,
        "reason": "",
    }
    duzeltilmis = _atik_moderasyon_duzelt(
        sonuc,
        baslik="5 litre kullanılmış bitkisel atık yağ verilecektir",
        aciklama="Restoranımızdan çıkan yağ geri dönüşüm için ücretsiz verilecektir.",
    )
    assert duzeltilmis["risk_skoru"] <= 30
    assert duzeltilmis["is_recyclable"] is True
    assert duzeltilmis["guvenli"] is True


def test_moderation_decision_thresholds():
    assert moderation_decision(20)["publish"] is True
    assert moderation_decision(20)["notify_admin"] is False
    assert moderation_decision(50)["notify_admin"] is True
    assert moderation_decision(75)["requires_review"] is True
    assert moderation_decision(95)["publish"] is False
    assert moderation_decision(95)["high_risk_review"] is True
    assert moderation_decision(95)["moderation_status"] == MODERATION_STATUS_PENDING_REVIEW


def test_high_risk_uygunsuz_rejected():
    assert resolve_moderation_status(95, uygunsuz=True) == MODERATION_STATUS_REJECTED
    assert resolve_moderation_status(95, uygunsuz=False) == MODERATION_STATUS_PENDING_REVIEW


def test_moderasyon_reddedildi_high_risk_blocks_publish():
    ai_sonuc = {"risk_skoru": 92, "uygunsuz": False, "moderation_status": "pending_review"}
    assert moderasyon_reddedildi(ai_sonuc, [], lambda x: None) is True


def test_moderasyon_reddedildi_mid_risk_allows_publish():
    ai_sonuc = {"risk_skoru": 75, "uygunsuz": False, "moderation_status": "pending_review"}
    assert moderasyon_reddedildi(ai_sonuc, [], lambda x: None) is False


# --- Geri dönüşüm olumlu örnekler ---

def test_recycling_purpose_aku():
    assert detect_recycling_purpose(
        baslik="Arızalı akü",
        aciklama="Geri dönüşüm için ücretsiz verilecektir",
    )


def test_recycling_adjustment_organik_atik():
    sonuc = {"risk_skoru": 70, "guvenli": False, "purpose": "recycling"}
    out = apply_recyclable_adjustment(
        sonuc,
        baslik="Organik atık",
        aciklama="Kompost için toplanacak",
        tur="atik",
    )
    assert out["risk_skoru"] <= 30
    assert out["is_recyclable"] is True


def test_recycling_adjustment_ai_purpose_field():
    # AI purpose tek başına yetmez; "hurda" sunucu tarafı amaç ifadesidir.
    sonuc = {"risk_skoru": 65, "is_recyclable": False, "purpose": "waste_collection"}
    assert qualifies_for_risk_adjustment(sonuc, baslik="Hurda metal", tur="atik")
    # Prompt injection: yalnızca AI bayrağı
    assert not qualifies_for_risk_adjustment(
        {"risk_skoru": 98, "is_recyclable": True, "purpose": "recycling", "uygunsuz": True},
        baslik="Zararsız görünen",
        aciklama="normal metin",
        tur="atik",
    )


def test_uygunsuz_never_adjusted_even_with_purpose_phrase():
    """Whitelist / amaç ifadesi uygunsuz=True iken riski düşüremez."""
    sonuc = {
        "risk_skoru": 98,
        "uygunsuz": True,
        "is_recyclable": True,
        "purpose": "recycling",
    }
    out = apply_recyclable_adjustment(
        sonuc,
        baslik="Silah geri dönüşüm için ücretsiz ver",
        aciklama="bertaraf",
        tur="atik",
    )
    assert out["risk_skoru"] == 98
    assert out.get("whitelist_applied") is False
    assert resolve_moderation_status(98, uygunsuz=True) == MODERATION_STATUS_REJECTED


# --- Zararlı içerik: risk düşürülmemeli ---

def test_harmful_content_not_adjusted():
    sonuc = {"risk_skoru": 95, "uygunsuz": True, "purpose": "unknown"}
    out = apply_recyclable_adjustment(
        sonuc,
        baslik="Uyuşturucu satışı",
        aciklama="İletişime geçin",
        tur="atik",
    )
    assert out["risk_skoru"] == 95


def test_harmful_high_risk_status_rejected():
    sonuc = {"risk_skoru": 98, "uygunsuz": True}
    out = apply_recyclable_adjustment(sonuc, baslik="Silah satılık", tur="atik")
    assert out["risk_skoru"] == 98
    assert resolve_moderation_status(98, uygunsuz=True) == MODERATION_STATUS_REJECTED


# --- Kelime tuzağı örnekleri ---

def test_word_trap_cam_bardak_kaynak_no_adjustment():
    sonuc = {"risk_skoru": 80, "guvenli": False}
    out = apply_recyclable_adjustment(
        sonuc,
        baslik="Cam bardak seti",
        aciklama="Temiz mutfak eşyası",
        tur="kaynak",
    )
    assert out["risk_skoru"] == 80


def test_word_trap_atik_yag_recycling_adjusted():
    sonuc = {"risk_skoru": 80, "guvenli": False}
    out = apply_recyclable_adjustment(
        sonuc,
        baslik="Atık yağ",
        aciklama="5 litre, geri dönüşüm için verilecek",
        tur="atik",
    )
    assert out["risk_skoru"] <= 30


def test_word_trap_pil_word_boundary():
    assert detect_waste_material_mention(baslik="Eski piller", aciklama="")
    assert not detect_waste_material_mention(baslik="Spilberg filmi", aciklama="")


def test_normalize_ai_response_includes_purpose():
    data = {
        "risk_score": 15,
        "category": "Plastik",
        "is_recyclable": True,
        "purpose": "recycling",
        "moderation_status": "approved",
        "reason": "Geri dönüşüm ilanı",
    }
    out = normalize_ai_ilan_response(
        data,
        ["Plastik", "Diğer"],
        tur="atik",
        baslik="Plastik şişeler",
        aciklama="Geri dönüşüm için",
    )
    assert out["purpose"] == "recycling"
    assert out["risk_skoru"] == 15
    assert out["is_recyclable"] is True
    assert out["moderation_status"] == "approved"
    assert out["kategori"] == "Plastik"
