from helpers import _atik_moderasyon_duzelt, _atik_baglami_var
from constants import AI_RISK_BLOCK_THRESHOLD


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
    assert duzeltilmis["risk_skoru"] < AI_RISK_BLOCK_THRESHOLD


def test_atik_moderasyon_duzelt_dusuk_risk_dokunmaz():
    sonuc = {"kategori": "Plastik", "risk_skoru": 20, "guvenli": True}
    duzeltilmis = _atik_moderasyon_duzelt(sonuc, kategori_secim="Plastik")
    assert duzeltilmis["risk_skoru"] == 20


def test_atik_moderasyon_duzelt_kaynak_baglami_yok():
    sonuc = {"kategori": "Diğer", "risk_skoru": 75, "guvenli": False}
    duzeltilmis = _atik_moderasyon_duzelt(sonuc, baslik="Antika vazo")
    assert duzeltilmis["risk_skoru"] == 75
    assert duzeltilmis["guvenli"] is False
