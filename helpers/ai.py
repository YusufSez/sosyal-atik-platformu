import logging
import os
import time

import google.genai as genai
from google.genai import types
from flask import current_app

from constants import (
    KATEGORILER_ATIK,
    KATEGORILER_KAYNAK,
    MESSAGE_AI_BLOCK_THRESHOLD,
)

from .image import resim_kontrol, resim_mime_tipi, resmi_bytes_oku
from .json_utils import json_cikar
from .parser import apply_vision_text_fallback
from .prompts import build_message_moderation_prompt

FREE_MODEL = "gemini-2.5-flash"
FREE_MODEL_BACKUP = "gemini-2.0-flash"
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_REQUEST_TIMEOUT_MS", "30000"))

logger = logging.getLogger("atikport.ai")


def _record_ai_health(model, success, t0, retry=0, request_type="vision", error=None):
    try:
        from services.ai_health import classify_ai_error, record_ai_request
        ms = int((time.perf_counter() - t0) * 1000)
        record_ai_request(
            model_name=model,
            success=success,
            response_time_ms=ms,
            request_type=request_type,
            error_type=classify_ai_error(error) if error else None,
            retry_count=retry,
        )
    except Exception:
        pass


def get_client():
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )


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
        "moderation_status": "approved",
        "is_recyclable": False,
        "reason": "",
        "hata": None,
    }

    def _bitir(s):
        from services.ai_moderation import (
            apply_recyclable_adjustment,
            resolve_moderation_status,
        )
        from constants import MODERATION_STATUS_REJECTED

        s = apply_recyclable_adjustment(
            s, baslik=baslik, aciklama=aciklama, kategori_secim=kategori_secim, tur=tur
        )
        s["moderation_status"] = s.get("moderation_status") or resolve_moderation_status(
            int(s.get("risk_skoru", 0))
        )
        s["guvenli"] = s["moderation_status"] != MODERATION_STATUS_REJECTED
        return s

    if not resim_kontrol(resim_yolu):
        sonuc["hata"] = "Görsel doğrulanamadı"
        return _bitir(sonuc)

    try:
        client = get_client()
        if not client:
            sonuc["hata"] = "GEMINI_API_KEY tanımlı değil"
            return _bitir(sonuc)

        from services.ai_moderation import build_vision_analysis_prompt, normalize_ai_ilan_response

        prompt = build_vision_analysis_prompt(tur, aciklama, baslik=baslik)
        kategoriler = KATEGORILER_KAYNAK if tur == "kaynak" else KATEGORILER_ATIK

        for model in [FREE_MODEL, FREE_MODEL_BACKUP]:
            retry = 1 if model != FREE_MODEL else 0
            t0 = time.perf_counter()
            try:
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

                data = json_cikar(text)
                if data:
                    try:
                        normalized = normalize_ai_ilan_response(
                            data,
                            kategoriler,
                            tur=tur,
                            baslik=baslik,
                            aciklama=aciklama,
                            kategori_secim=kategori_secim,
                        )
                        sonuc.update(normalized)
                        _record_ai_health(model, True, t0, retry, "vision")
                        return _bitir(sonuc)

                    except (TypeError, ValueError):
                        _record_ai_health(model, False, t0, retry, "vision")
                        continue

                apply_vision_text_fallback(text, kategoriler, sonuc)

                _record_ai_health(model, True, t0, retry, "vision")
                return _bitir(sonuc)

            except Exception as e:
                _record_ai_health(model, False, t0, retry, "vision", error=e)
                sonuc["hata"] = f"{model} hatası: {type(e).__name__}: {str(e)}"
                logger.warning("Görsel analiz hatası (%s): %s", model, sonuc["hata"])
                continue

        sonuc["hata"] = "AI servisi kullanılamıyor"
        logger.error("Görsel analiz: tüm modeller başarısız (%s)", resim_yolu)
        sonuc["guvenli"] = False
        sonuc["risk_skoru"] = max(sonuc["risk_skoru"], 80)
        return _bitir(sonuc)

    except Exception as e:
        sonuc["hata"] = str(e)
        logger.exception("Görsel analiz beklenmeyen hata")
        sonuc["guvenli"] = False
        sonuc["risk_skoru"] = max(sonuc["risk_skoru"], 80)
        return _bitir(sonuc)


def ai_metin_moderasyon(baslik, aciklama, tur="atik"):
    """Görsel olmadan metin tabanlı moderasyon."""
    from services.ai_moderation import build_text_moderation_prompt, normalize_ai_ilan_response

    kategoriler = KATEGORILER_ATIK if tur == "atik" else KATEGORILER_KAYNAK
    sonuc = {
        "risk_skoru": 0,
        "guvenli": True,
        "moderation_status": "approved",
        "is_recyclable": False,
        "reason": "",
        "hata": None,
    }
    metin = f"{baslik or ''} {aciklama or ''}".strip()
    if not metin:
        sonuc["guvenli"] = False
        sonuc["risk_skoru"] = 50
        return sonuc

    try:
        client = get_client()
        if not client:
            sonuc["hata"] = "GEMINI_API_KEY tanımlı değil"
            sonuc["guvenli"] = True
            sonuc["risk_skoru"] = min(sonuc.get("risk_skoru", 0), 40)
            return sonuc
        prompt = build_text_moderation_prompt(baslik, aciklama, tur=tur)

        for model in [FREE_MODEL, FREE_MODEL_BACKUP]:
            retry = 1 if model != FREE_MODEL else 0
            t0 = time.perf_counter()
            try:
                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                text = result.text.strip()
                data = json_cikar(text)
                if data:
                    normalized = normalize_ai_ilan_response(
                        data,
                        kategoriler,
                        tur=tur,
                        baslik=baslik,
                        aciklama=aciklama,
                    )
                    sonuc.update(normalized)
                    _record_ai_health(model, True, t0, retry, "text")
                    return sonuc
                _record_ai_health(model, True, t0, retry, "text")
            except Exception as e:
                _record_ai_health(model, False, t0, retry, "text", error=e)
                sonuc["hata"] = str(e)
                continue
    except Exception as e:
        sonuc["hata"] = str(e)

    sonuc["guvenli"] = True
    sonuc["risk_skoru"] = min(sonuc.get("risk_skoru", 0), 40)
    return sonuc


def ai_mesaj_moderasyon(metin: str) -> dict:
    """
    Sohbet mesajları için Gemini tabanlı içerik denetimi.
    Dönüş: uygun, risk_skoru, kategori, mesaj (kullanıcıya), kaynak (ai|fallback), hata
    """
    sonuc = {
        "uygun": True,
        "risk_skoru": 0,
        "kategori": None,
        "mesaj": "",
        "kaynak": "ai",
        "hata": None,
    }
    metin = (metin or "").strip()
    if not metin:
        return sonuc

    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        sonuc["kaynak"] = "fallback"
        sonuc["hata"] = "GEMINI_API_KEY tanımlı değil"
        return sonuc

    prompt = build_message_moderation_prompt(metin)

    try:
        client = get_client()
        for model in [FREE_MODEL, FREE_MODEL_BACKUP]:
            try:
                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                data = json_cikar((result.text or "").strip())
                if not data:
                    continue

                risk = min(max(int(data.get("risk_skoru", 0)), 0), 100)
                uygunsuz = bool(data.get("uygunsuz", False))
                sonuc["risk_skoru"] = risk
                sonuc["kategori"] = data.get("kategori")
                sonuc["uygun"] = not uygunsuz and risk < MESSAGE_AI_BLOCK_THRESHOLD

                if not sonuc["uygun"]:
                    aciklama = (data.get("aciklama") or "").strip()
                    sonuc["mesaj"] = (
                        "Mesajınız yapay zeka içerik denetimi tarafından uygunsuz bulundu. "
                        "Lütfen saygılı bir dil kullanın."
                        + (f" ({aciklama})" if aciklama else "")
                    )
                return sonuc
            except Exception as e:
                sonuc["hata"] = f"{model}: {e}"
                logger.warning("Mesaj moderasyon hatası (%s): %s", model, e)
                continue
    except Exception as e:
        sonuc["hata"] = str(e)
        logger.warning("Mesaj moderasyon başarısız: %s", e)

    sonuc["kaynak"] = "fallback"
    return sonuc


def ai_kategori_bul(resim_yolu, aciklama=None):
    """Geriye uyumlu eski fonksiyon - sadece kategori döndürür"""
    sonuc = ai_tam_analiz(resim_yolu, "kaynak", aciklama)
    return sonuc.get("kategori", "Diğer")


def ai_moderasyon_kontrol(aciklama, resim_yolu):
    """Geriye uyumlu eski fonksiyon - sadece risk skoru döndürür"""
    sonuc = ai_tam_analiz(resim_yolu, "kaynak", aciklama)
    return sonuc.get("risk_skoru", 0)
