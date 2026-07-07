import json
import os
import re

import google.genai as genai
from google.genai import types
from flask import current_app
from PIL import Image

from constants import (
    AI_RISK_BLOCK_THRESHOLD,
    DURUMLAR_KAYNAK,
    KATEGORILER_ATIK,
    KATEGORILER_KAYNAK,
)

FREE_MODEL = "gemini-2.5-flash"
FREE_MODEL_BACKUP = "gemini-2.0-flash"

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def resim_mime_tipi(resim_yolu):
    ext = os.path.splitext(resim_yolu)[1].lower()
    return MIME_MAP.get(ext, "image/jpeg")


def json_cikar(text):
    """AI yanıtından JSON nesnesini çıkarır (iç içe yapılar dahil)."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None

# ------------------------
# RESİM BYTES
# ------------------------
def resmi_bytes_oku(resim_yolu):
    with open(resim_yolu, "rb") as f:
        return f.read()

# ------------------------
# RESİM VALIDASYON
# ------------------------
def resim_kontrol(resim_yolu):
    try:
        with Image.open(resim_yolu) as img:
            img.verify()
        with Image.open(resim_yolu) as img:
            return img.format in ("JPEG", "PNG", "WEBP")
    except Exception:
        return False

# ------------------------
# AI CLIENT
# ------------------------
def get_client():
    api_key = current_app.config.get("GEMINI_API_KEY")
    return genai.Client(api_key=api_key)


_ATIK_ANAHTAR_KELIMELER = (
    "pil", "akü", "aku", "batarya", "battery", "şarj", "sarj",
    "atık", "atik", "hurda", "geri dönüşüm", "geri donusum", "recycle",
    "elektronik atık", "e-atık", "e-atik", "plastik", "kağıt", "kagit",
    "cam kırığı", "cam kirigi", "metal", "organik", "tekstil", "ahşap", "ahsap",
)


def _metin_normalize(metin):
    if not metin:
        return ""
    return metin.lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")


def _atik_baglami_var(baslik=None, aciklama=None, kategori_secim=None, ai_kategori=None):
    if kategori_secim and kategori_secim.strip() in KATEGORILER_ATIK:
        return True
    if ai_kategori and ai_kategori in KATEGORILER_ATIK and ai_kategori != "Diğer":
        return True
    birlesik = _metin_normalize(f"{baslik or ''} {aciklama or ''}")
    return any(kw in birlesik for kw in _ATIK_ANAHTAR_KELIMELER)


def _atik_moderasyon_duzelt(sonuc, baslik=None, aciklama=None, kategori_secim=None):
    """Atık/pil fotoğraflarında AI'nın yüksek verdiği risk skorlarını düşürür."""
    if not _atik_baglami_var(baslik, aciklama, kategori_secim, sonuc.get("kategori")):
        return sonuc
    risk = sonuc.get("risk_skoru", 0)
    if risk < 35:
        return sonuc
    sonuc = dict(sonuc)
    sonuc["risk_skoru"] = min(risk, 30)
    sonuc["guvenli"] = sonuc["risk_skoru"] < AI_RISK_BLOCK_THRESHOLD
    return sonuc


# ------------------------
# AI KAPSAMLI ANALİZ
# ------------------------
def ai_tam_analiz(resim_yolu, tur="kaynak", aciklama=None, baslik=None, kategori_secim=None):
    """
    Hem moderasyon hem kategori hem de durum analizi yapar.
    tur: 'kaynak' veya 'atik'
    """
    sonuc = {
        "kategori": "Diğer",
        "durum": "Kullanılmış",
        "risk_skoru": 0,
        "guvenli": True,
        "hata": None
    }

    def _bitir(s):
        if tur == "atik":
            return _atik_moderasyon_duzelt(s, baslik=baslik, aciklama=aciklama, kategori_secim=kategori_secim)
        return s
    
    # Resim kontrolü
    if not resim_kontrol(resim_yolu):
        sonuc["hata"] = "Görsel doğrulanamadı"
        return _bitir(sonuc)
    
    try:
        client = get_client()
        
        # Kategori seçimi
        if tur == "kaynak":
            kategoriler = KATEGORILER_KAYNAK
            kategori_template = """
KAYNAK KATEGORİLERİ:
{muse_categories}

Yukarıdaki kategorilerden birini seç."""

            durum_template = """
DURUM TAHMİNİ (sadece kaynaklar için):
- Temiz: Yeni veya çok az kullanılmış
- Kullanılmış: Normal kullanım izleri var
- Hasarlı: Belirgin hasar veya kusur var

Durumu tahmin et."
        """
        else:
            kategoriler = KATEGORILER_ATIK
            kategori_template = """
ATIK KATEGORİLERİ:
{waste_categories}

Yukarıdaki kategorilerden birini seç."""

            durum_template = ""
        
        # Kapsamlı analiz prompt'u
        kategori_str = "\n".join([f"- {k}" for k in kategoriler])
        
        # Durum kısmını ayrı hazırla
        if tur == "kaynak":
            durum_kismi = """
2. DURUM TAHMİNİ:
- Temiz: Yeni veya çok az kullanılmış
- Kullanılmış: Normal kullanım izleri var
- Hasarlı: Belirgin hasar veya kusur var

Durumu tahmin et."""
            moderasyon_kismi = """
3. UYGUNSUZLUK KONTROLÜ: Görselde veya içerikte uygunsuz, yasadışı veya zararlı bir şey var mı? (Evet/Hayır)

4. RİSK SKORU: 0-100 arası (0=güvenli, 100=çok riskli)"""
        else:
            durum_kismi = ""
            moderasyon_kismi = """
3. UYGUNSUZLUK KONTROLÜ: Bu bir GERİ DÖNÜŞÜM / ATIK PAYLAŞIM platformudur.
Pil, akü, elektronik atık, cam kırığı, metal hurda ve benzeri atık fotoğrafları NORMAL içeriktir (uygunsuz=false).
Sadece çıplaklık, şiddet, nefret, uyuşturucu, silah veya platformla ilgisiz içerik için uygunsuz=true ver.

4. RİSK SKORU: Evsel/geri dönüşüm atığı fotoğrafları için 0-35 arası ver.
Sadece gerçekten yasadışı veya uygunsuz içerik için 70 üzeri ver."""
        
        prompt = f"""Sen bir atık ve kaynak paylaşım platformu için AI analiz asistanısın.

GÖREV: Görseli analiz et ve aşağıdaki bilgileri JSON formatında döndür.

1. KATEGORİ BELİRLEME:
{kategori_str}
{durum_kismi}
{moderasyon_kismi}

Ek bilgi (varsa): {aciklama if aciklama else "yok"}

JSON formatında döndür:
{{
    "kategori": "seçilen kategori",
    "uygunsuz": true/false,
    "risk_skoru": 0-100 arası sayı,
    "aciklama": "Kısa bir açıklama (opsiyonel)"
}}

ÖNEMLİ: SADECE JSON DÖNDÜR, BAŞKA BİRŞEY YAZMA!"""

        for model in [FREE_MODEL, FREE_MODEL_BACKUP]:
            try:
                # Resmi bytes olarak oku
                image_bytes = resmi_bytes_oku(resim_yolu)
                
                result = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(
                            parts=[
                                types.Part(text=prompt),
                                types.Part(inline_data=types.Blob(
                                    data=image_bytes, mime_type=resim_mime_tipi(resim_yolu)
                                ))
                            ]
                        )
                    ]
                )
                
                text = result.text.strip()
                
                # JSON çıkarma
                data = json_cikar(text)
                if data:
                    try:
                        
                        # Kategori doğrulama
                        if data.get("kategori"):
                            for k in kategoriler:
                                if k.lower() in data["kategori"].lower():
                                    sonuc["kategori"] = k
                                    break
                        
                        # Durum doğrulama (sadece kaynak için)
                        if tur == "kaynak" and data.get("durum"):
                            for d in DURUMLAR_KAYNAK:
                                if d.lower() in data["durum"].lower():
                                    sonuc["durum"] = d
                                    break
                        
                        # Risk skoru
                        risk = data.get("risk_skoru", 0)
                        sonuc["risk_skoru"] = min(max(int(risk), 0), 100)
                        
                        # Güvenlik kontrolü
                        sonuc["guvenli"] = (
                            data.get("uygunsuz", False) is False
                            and sonuc["risk_skoru"] < AI_RISK_BLOCK_THRESHOLD
                        )
                        
                        return _bitir(sonuc)

                    except (TypeError, ValueError):
                        continue
                
                # Fallback: text'i parse et
                text_lower = text.lower()
                
                # Kategori bul
                for k in kategoriler:
                    if k.lower() in text_lower:
                        sonuc["kategori"] = k
                        break
                
                # Risk skoru bul
                scores = re.findall(r'\b(\d{1,3})\b', text)
                for s in scores:
                    score = int(s)
                    if 0 <= score <= 100:
                        sonuc["risk_skoru"] = score
                        break
                
                # Uygunsuzluk kontrolü
                if "uygunsuz" in text_lower or "riskli" in text_lower or "zararlı" in text_lower:
                    sonuc["guvenli"] = False
                    sonuc["risk_skoru"] = max(sonuc["risk_skoru"], 50)
                
                return _bitir(sonuc)
                
            except Exception as e:
                sonuc["hata"] = f"{model} hatası: {type(e).__name__}: {str(e)}"
                continue
        
        sonuc["hata"] = "AI servisi kullanılamıyor"
        sonuc["guvenli"] = False
        sonuc["risk_skoru"] = max(sonuc["risk_skoru"], 80)
        return _bitir(sonuc)
        
    except Exception as e:
        sonuc["hata"] = str(e)
        sonuc["guvenli"] = False
        sonuc["risk_skoru"] = max(sonuc["risk_skoru"], 80)
        return _bitir(sonuc)


def ai_metin_moderasyon(baslik, aciklama):
    """Görsel olmadan metin tabanlı moderasyon."""
    sonuc = {"risk_skoru": 0, "guvenli": True, "hata": None}
    metin = f"{baslik or ''} {aciklama or ''}".strip()
    if not metin:
        sonuc["guvenli"] = False
        sonuc["risk_skoru"] = 50
        return sonuc

    try:
        client = get_client()
        prompt = f"""Aşağıdaki ilan metnini moderasyon için değerlendir.
Metin: {metin}

JSON döndür: {{"uygunsuz": true/false, "risk_skoru": 0-100}}
SADECE JSON yaz."""

        for model in [FREE_MODEL, FREE_MODEL_BACKUP]:
            try:
                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                text = result.text.strip()
                data = json_cikar(text)
                if data:
                    risk = min(max(int(data.get("risk_skoru", 0)), 0), 100)
                    sonuc["risk_skoru"] = risk
                    sonuc["guvenli"] = (
                        data.get("uygunsuz", False) is False
                        and risk < AI_RISK_BLOCK_THRESHOLD
                    )
                    return sonuc
            except Exception as e:
                sonuc["hata"] = str(e)
                continue
    except Exception as e:
        sonuc["hata"] = str(e)

    sonuc["guvenli"] = False
    sonuc["risk_skoru"] = 75
    return sonuc


def moderasyon_kontrol(ai_sonuc, baslik=None, aciklama=None, resim_var=False):
    """Görsel + metin moderasyonunu birleştirir."""
    if resim_var and ai_sonuc.get("hata"):
        ai_sonuc["guvenli"] = False
        ai_sonuc["risk_skoru"] = max(ai_sonuc.get("risk_skoru", 0), 80)
    if not resim_var:
        metin_sonuc = ai_metin_moderasyon(baslik, aciklama)
        ai_sonuc["risk_skoru"] = max(ai_sonuc.get("risk_skoru", 0), metin_sonuc["risk_skoru"])
        ai_sonuc["guvenli"] = metin_sonuc.get("guvenli", False)
        if metin_sonuc.get("hata"):
            ai_sonuc["hata"] = metin_sonuc["hata"]
    return ai_sonuc

# ------------------------
# AI KATEGORİ (Eski uyumlu)
# ------------------------
def ai_kategori_bul(resim_yolu, aciklama=None):
    """Geriye uyumlu eski fonksiyon - sadece kategori döndürür"""
    sonuc = ai_tam_analiz(resim_yolu, "kaynak", aciklama)
    return sonuc.get("kategori", "Diğer")

# ------------------------
# MODERASYON (Geliştirilmiş)
# ------------------------
def ai_moderasyon_kontrol(aciklama, resim_yolu):
    """Geriye uyumlu eski fonksiyon - sadece risk skoru döndürür"""
    sonuc = ai_tam_analiz(resim_yolu, "kaynak", aciklama)
    return sonuc.get("risk_skoru", 0)

# ------------------------
# GELİŞMİŞ MODERASYON
# ------------------------
def gelismis_moderasyon(resim_yolu, aciklama=None):
    """
    Kapsamlı moderasyon kontrolü yapar.
    (status): guvenli, şüpheli, riskli
    """
    sonuc = ai_tam_analiz(resim_yolu, "kaynak", aciklama)
    
    if sonuc["risk_skoru"] < 30:
        return {
            "status": "guvenli",
            "skor": sonuc["risk_skoru"],
            "mesaj": "İçerik güvenli görünüyor."
        }
    elif sonuc["risk_skoru"] < AI_RISK_BLOCK_THRESHOLD:
        return {
            "status": "suspicious",
            "skor": sonuc["risk_skoru"],
            "mesaj": "İçerik şüpheli görünüyor, manuel inceleme önerilir."
        }
    else:
        return {
            "status": "riskli",
            "skor": sonuc["risk_skoru"],
            "mesaj": "İçerik riskli bulundu, paylaşım engellendi."
        }

