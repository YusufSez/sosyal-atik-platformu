"""Versiyonlu AI moderasyon analizi kaydetme ve yeniden analiz."""

from __future__ import annotations

import json
from typing import Any

from constants import AI_MODERATION_MODEL_DEFAULT, AI_PROMPT_VERSION
from extensions import db
from helpers import FREE_MODEL, ai_metin_moderasyon
from models import Atik, IlanModerasyonAnaliz, Kaynak
from services.ai_moderation import enrich_explainability
from services.ilan_images import fotograf_moderasyonu, ilan_fotograf_listesi
from services.ilan_moderation import ilan_moderasyon_alanlarini_uygula
from services.moderation_photos import analyze_listing_photos, merge_photo_analyses
from services.moderation_timeline import analiz_timeline_olaylari_ekle, timeline_ekle
from utils import utc_now


def _ilan_getir(tur: str, ilan_id: int):
    if tur == "kaynak":
        return Kaynak.query.get(ilan_id)
    return Atik.query.get(ilan_id)


def _sonraki_version(tur: str, ilan_id: int) -> int:
    q = IlanModerasyonAnaliz.query
    if tur == "kaynak":
        q = q.filter_by(kaynak_id=ilan_id)
    else:
        q = q.filter_by(atik_id=ilan_id)
    last = q.order_by(IlanModerasyonAnaliz.analysis_version.desc()).first()
    return (last.analysis_version + 1) if last else 1


def _mevcut_analizleri_pasif_yap(tur: str, ilan_id: int) -> None:
    q = IlanModerasyonAnaliz.query.filter_by(is_current=True)
    if tur == "kaynak":
        q = q.filter_by(kaynak_id=ilan_id)
    else:
        q = q.filter_by(atik_id=ilan_id)
    for row in q.all():
        row.is_current = False


def analiz_kaydet(
    ilan,
    tur: str,
    ai_sonuc: dict,
    *,
    photo_analyses: list[dict] | None = None,
    text_analysis: dict | None = None,
    vision_analysis: dict | None = None,
    triggered_by: str = "upload",
    admin_user_id: int | None = None,
    model_name: str | None = None,
    prompt_version: str | None = None,
) -> IlanModerasyonAnaliz:
    """Yeni analiz versiyonu kaydeder; önceki is_current=false yapılır."""
    ilan_id = ilan.id
    _mevcut_analizleri_pasif_yap(tur, ilan_id)
    version = _sonraki_version(tur, ilan_id)
    model = model_name or FREE_MODEL or AI_MODERATION_MODEL_DEFAULT
    prompt = prompt_version or AI_PROMPT_VERSION

    matched_rules = ai_sonuc.get("matched_rules") or []
    spam_reasons = ai_sonuc.get("spam_reasons") or []
    dup_reasons = ai_sonuc.get("duplicate_reasons") or []
    dup_matches = ai_sonuc.get("duplicate_matches") or []
    photo_hashes = ai_sonuc.get("photo_hashes") or []
    kayit = IlanModerasyonAnaliz(
        tur=tur,
        kaynak_id=ilan_id if tur == "kaynak" else None,
        atik_id=ilan_id if tur == "atik" else None,
        analysis_version=version,
        is_current=True,
        model_name=model,
        prompt_version=prompt,
        initial_risk=int(ai_sonuc.get("initial_risk", ai_sonuc.get("risk_skoru", 0))),
        final_risk=int(ai_sonuc.get("final_risk", ai_sonuc.get("risk_skoru", 0))),
        risk_adjustment=int(ai_sonuc.get("risk_adjustment", 0)),
        category=ai_sonuc.get("kategori"),
        purpose=ai_sonuc.get("purpose"),
        confidence=float(ai_sonuc.get("confidence", 0.85)),
        is_recyclable=bool(ai_sonuc.get("is_recyclable")),
        matched_rules_json=json.dumps(matched_rules, ensure_ascii=False),
        reason=ai_sonuc.get("reason"),
        moderation_status=ai_sonuc.get("moderation_status", "approved"),
        whitelist_applied=bool(ai_sonuc.get("whitelist_applied")),
        risk_adjustment_reason=ai_sonuc.get("risk_adjustment_reason"),
        text_analysis_json=json.dumps(text_analysis or {}, ensure_ascii=False),
        vision_analysis_json=json.dumps(vision_analysis or {}, ensure_ascii=False),
        photo_analyses_json=json.dumps(photo_analyses or [], ensure_ascii=False),
        raw_json=json.dumps(ai_sonuc, ensure_ascii=False, default=str),
        spam_score=int(ai_sonuc.get("spam_score", 0)) if ai_sonuc.get("spam_score") is not None else None,
        duplicate_score=int(ai_sonuc.get("duplicate_score", 0)) if ai_sonuc.get("duplicate_score") is not None else None,
        spam_reasons_json=json.dumps(spam_reasons, ensure_ascii=False),
        duplicate_reasons_json=json.dumps(dup_reasons, ensure_ascii=False),
        duplicate_matches_json=json.dumps(dup_matches, ensure_ascii=False),
        upload_ip=ai_sonuc.get("upload_ip"),
        upload_user_agent=ai_sonuc.get("upload_user_agent"),
        device_fingerprint=ai_sonuc.get("device_fingerprint"),
        photo_hashes_json=json.dumps(photo_hashes, ensure_ascii=False),
        triggered_by=triggered_by,
        admin_user_id=admin_user_id,
        created_at=utc_now(),
    )
    db.session.add(kayit)
    db.session.flush()
    analiz_timeline_olaylari_ekle(
        tur, ilan_id, ai_sonuc, kayit.id, triggered_by, model, prompt
    )
    return kayit


def guncel_analiz(tur: str, ilan_id: int) -> IlanModerasyonAnaliz | None:
    q = IlanModerasyonAnaliz.query.filter_by(is_current=True)
    if tur == "kaynak":
        return q.filter_by(kaynak_id=ilan_id).first()
    return q.filter_by(atik_id=ilan_id).first()


def analiz_gecmisi(tur: str, ilan_id: int) -> list[IlanModerasyonAnaliz]:
    q = IlanModerasyonAnaliz.query
    if tur == "kaynak":
        q = q.filter_by(kaynak_id=ilan_id)
    else:
        q = q.filter_by(atik_id=ilan_id)
    return q.order_by(IlanModerasyonAnaliz.analysis_version.desc()).all()


def analiz_dict(analiz: IlanModerasyonAnaliz | None) -> dict[str, Any]:
    """Admin detay ekranı için analiz verisi."""
    if not analiz:
        return {}
    try:
        matched_rules = json.loads(analiz.matched_rules_json or "[]")
    except json.JSONDecodeError:
        matched_rules = []
    try:
        photo_analyses = json.loads(analiz.photo_analyses_json or "[]")
    except json.JSONDecodeError:
        photo_analyses = []
    try:
        text_analysis = json.loads(analiz.text_analysis_json or "{}")
    except json.JSONDecodeError:
        text_analysis = {}
    try:
        vision_analysis = json.loads(analiz.vision_analysis_json or "{}")
    except json.JSONDecodeError:
        vision_analysis = {}
    try:
        raw_json = json.loads(analiz.raw_json or "{}")
    except json.JSONDecodeError:
        raw_json = {}
    try:
        spam_reasons = json.loads(analiz.spam_reasons_json or "[]")
    except json.JSONDecodeError:
        spam_reasons = []
    try:
        duplicate_reasons = json.loads(analiz.duplicate_reasons_json or "[]")
    except json.JSONDecodeError:
        duplicate_reasons = []
    try:
        duplicate_matches = json.loads(analiz.duplicate_matches_json or "[]")
    except json.JSONDecodeError:
        duplicate_matches = []
    from services.moderation_explainability import compute_explainability_signals
    pos = raw_json.get("positive_signals")
    neg = raw_json.get("negative_signals")
    if pos is None or neg is None:
        pos, neg = compute_explainability_signals(raw_json)
    return {
        "id": analiz.id,
        "analysis_version": analiz.analysis_version,
        "is_current": analiz.is_current,
        "model_name": analiz.model_name,
        "prompt_version": analiz.prompt_version,
        "initial_risk": analiz.initial_risk,
        "final_risk": analiz.final_risk,
        "risk_adjustment": analiz.risk_adjustment,
        "category": analiz.category,
        "purpose": analiz.purpose,
        "confidence": analiz.confidence,
        "is_recyclable": analiz.is_recyclable,
        "matched_rules": matched_rules,
        "reason": analiz.reason,
        "moderation_status": analiz.moderation_status,
        "whitelist_applied": analiz.whitelist_applied,
        "risk_adjustment_reason": analiz.risk_adjustment_reason,
        "text_analysis": text_analysis,
        "vision_analysis": vision_analysis,
        "photo_analyses": photo_analyses,
        "raw_json": raw_json,
        "spam_score": analiz.spam_score,
        "duplicate_score": analiz.duplicate_score,
        "spam_reasons": spam_reasons,
        "duplicate_reasons": duplicate_reasons,
        "duplicate_matches": duplicate_matches,
        "positive_signals": pos,
        "negative_signals": neg,
        "upload_ip": analiz.upload_ip,
        "device_fingerprint": analiz.device_fingerprint,
        "triggered_by": analiz.triggered_by,
        "created_at": analiz.created_at,
    }


def tam_ilan_analizi_yap(
    ilan,
    tur: str,
    *,
    triggered_by: str = "upload",
    admin_user_id: int | None = None,
    analyze_photo_fn=None,
    analyze_text_fn=None,
) -> dict:
    """Görsel + metin birleşik analiz; explainability alanlarıyla döner."""
    baslik = getattr(ilan, "baslik", "")
    aciklama = getattr(ilan, "aciklama", "")
    kategori_secim = getattr(ilan, "kategori", None) if tur == "atik" else None
    fotolar = ilan_fotograf_listesi(ilan)

    if analyze_text_fn is None:
        analyze_text_fn = ai_metin_moderasyon
    if analyze_photo_fn is None:
        from helpers import ai_tam_analiz
        analyze_photo_fn = ai_tam_analiz

    text_sonuc = analyze_text_fn(baslik, aciklama, tur=tur) if (baslik or aciklama) else {}
    photo_analyses = analyze_listing_photos(
        fotolar, tur, baslik, aciklama, analyze_fn=analyze_photo_fn
    )
    vision_summary = merge_photo_analyses(photo_analyses)

    if photo_analyses:
        ai_sonuc = dict(photo_analyses[0].get("raw") or {})
    else:
        ai_sonuc = {"risk_skoru": 0, "guvenli": True, "moderation_status": "approved"}

    if text_sonuc:
        ai_sonuc["risk_skoru"] = max(
            int(ai_sonuc.get("risk_skoru", 0)),
            int(text_sonuc.get("risk_skoru", 0)),
        )
        for key in ("reason", "purpose", "is_recyclable", "uygunsuz", "confidence", "matched_rules"):
            if text_sonuc.get(key):
                ai_sonuc[key] = text_sonuc[key]

    ai_sonuc = fotograf_moderasyonu(
        ai_sonuc, baslik, aciklama, fotolar, tur=tur
    )
    initial = int(ai_sonuc.get("initial_risk", ai_sonuc.get("risk_skoru", 0)))
    ai_sonuc = enrich_explainability(
        ai_sonuc,
        baslik=baslik,
        aciklama=aciklama,
        kategori_secim=kategori_secim,
        tur=tur,
        initial_risk=initial,
    )
    ai_sonuc["text_analysis"] = text_sonuc
    ai_sonuc["vision_analysis"] = vision_summary
    ai_sonuc["photo_analyses"] = photo_analyses

    from services.moderation_signals import enrich_upload_signals
    enrich_upload_signals(
        ai_sonuc,
        tur=tur,
        ilan_id=getattr(ilan, "id", None),
        baslik=baslik,
        aciklama=aciklama,
        user_id=getattr(ilan, "user_id", 0),
        kategori=kategori_secim or getattr(ilan, "kategori", None),
        latitude=getattr(ilan, "latitude", None),
        longitude=getattr(ilan, "longitude", None),
        photo_files=fotolar,
    )
    return ai_sonuc


def kaydet_ilk_analiz(
    ilan,
    tur: str,
    ai_sonuc: dict,
    photo_files: list[str] | None = None,
    triggered_by: str = "upload",
    admin_user_id: int | None = None,
) -> IlanModerasyonAnaliz:
    """Upload/edit sonrası analiz kaydı."""
    photo_analyses = ai_sonuc.get("photo_analyses")
    if photo_analyses is None and photo_files:
        photo_analyses = analyze_listing_photos(
            photo_files,
            tur,
            getattr(ilan, "baslik", ""),
            getattr(ilan, "aciklama", ""),
        )
    return analiz_kaydet(
        ilan,
        tur,
        ai_sonuc,
        photo_analyses=photo_analyses,
        text_analysis=ai_sonuc.get("text_analysis"),
        vision_analysis=ai_sonuc.get("vision_analysis"),
        triggered_by=triggered_by,
        admin_user_id=admin_user_id,
    )


def yeniden_ai_analizi(
    tur: str,
    ilan_id: int,
    admin_user_id: int,
    *,
    analyze_photo_fn=None,
    analyze_text_fn=None,
) -> tuple[dict, IlanModerasyonAnaliz]:
    """Admin tetiklemeli yeniden analiz; eski kayıtlar korunur."""
    ilan = _ilan_getir(tur, ilan_id)
    if not ilan:
        raise ValueError("İlan bulunamadı")

    ai_sonuc = tam_ilan_analizi_yap(
        ilan,
        tur,
        triggered_by="admin_reanalyze",
        admin_user_id=admin_user_id,
        analyze_photo_fn=analyze_photo_fn,
        analyze_text_fn=analyze_text_fn,
    )
    ilan_moderasyon_alanlarini_uygula(ilan, ai_sonuc)
    kayit = analiz_kaydet(
        ilan,
        tur,
        ai_sonuc,
        photo_analyses=ai_sonuc.get("photo_analyses"),
        text_analysis=ai_sonuc.get("text_analysis"),
        vision_analysis=ai_sonuc.get("vision_analysis"),
        triggered_by="admin_reanalyze",
        admin_user_id=admin_user_id,
    )
    return ai_sonuc, kayit
