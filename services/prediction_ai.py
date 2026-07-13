"""Tahmin sonuçlarından Gemini / kural tabanlı Türkçe yorum üretimi."""

from __future__ import annotations

import json
import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.prediction_engine import (
    FORECAST_HORIZONS_DAYS,
    METRIC_KEYS,
    run_multi_lookback_forecast,
    run_statistical_forecast,
)

logger = logging.getLogger("atikport.prediction_ai")

_TREND_TR = {
    "yukselis": "yükseliş",
    "dusus": "düşüş",
    "stabil": "stabil",
}
_RISK_TR = {
    "dusuk": "düşük",
    "orta": "orta",
    "yuksek": "yüksek",
}


def _format_value(metric: dict) -> str:
    unit = metric.get("unit") or ""
    pred = metric.get("predicted")
    if pred is None:
        return "—"
    if unit == "%":
        return f"%{pred}"
    if unit:
        return f"{pred} {unit}"
    return str(pred)


def _rule_comment_for_metric(metric: dict) -> str:
    label = metric.get("label") or metric.get("metric") or "Metrik"
    horizon = metric.get("horizon_label") or f"{metric.get('horizon_days', '?')} gün"
    trend = _TREND_TR.get(metric.get("trend") or "", metric.get("trend") or "stabil")
    risk = _RISK_TR.get(metric.get("risk") or "", metric.get("risk") or "orta")
    conf = metric.get("confidence_pct")
    ci = metric.get("confidence_interval") or {}
    change = metric.get("change_pct")
    value = _format_value(metric)

    parts = [
        f"{horizon} için {label} tahmini {value}",
        f"trend {trend}",
        f"risk {risk}",
    ]
    if conf is not None:
        parts.append(f"güven %{conf:.0f}")
    if ci.get("low") is not None and ci.get("high") is not None:
        unit = metric.get("unit") or ""
        if unit == "%":
            parts.append(f"aralık %{ci['low']}–%{ci['high']}")
        elif unit:
            parts.append(f"aralık {ci['low']}–{ci['high']} {unit}")
        else:
            parts.append(f"aralık {ci['low']}–{ci['high']}")
    if change is not None:
        yon = "artış" if change >= 0 else "azalış"
        parts.append(f"baz aya göre %{abs(change):.0f} {yon}")

    if metric.get("metric") == "kategori_artisi" and metric.get("kategori"):
        parts.insert(1, f"öne çıkan kategori: {metric['kategori']}")

    return "; ".join(parts) + "."


def _apply_rule_comments(forecast_payload: dict) -> list[str]:
    """Her ufuk × metrik için kural tabanlı yorum; forecasts içine yazar."""
    narratives = []
    forecasts = forecast_payload.get("forecasts") or {}
    for days in FORECAST_HORIZONS_DAYS:
        block = forecasts.get(str(days)) or {}
        for key in METRIC_KEYS:
            metric = block.get(key)
            if not isinstance(metric, dict):
                continue
            comment = _rule_comment_for_metric(metric)
            metric["ai_yorum"] = comment
            # Alias
            if key == "kategori_artisi" and isinstance(block.get("en_yogun_kategori"), dict):
                block["en_yogun_kategori"]["ai_yorum"] = comment
            if days in (7, 30, 90) and key in ("atik_miktari", "teslim_orani", "kategori_artisi"):
                narratives.append(comment)
    if not narratives:
        narratives.append(
            "Yeterli tarihsel veri birikince istatistiksel tahminler burada görünecek."
        )
    return narratives[:8]


def _compact_for_gemini(primary: dict) -> dict:
    out = {"lookback_months": primary.get("lookback_months"), "horizons": {}}
    forecasts = primary.get("forecasts") or {}
    for days in FORECAST_HORIZONS_DAYS:
        block = forecasts.get(str(days)) or {}
        slim = {}
        for key in METRIC_KEYS:
            m = block.get(key) or {}
            if not m:
                continue
            slim[key] = {
                "label": m.get("label"),
                "predicted": m.get("predicted"),
                "unit": m.get("unit"),
                "change_pct": m.get("change_pct"),
                "confidence_pct": m.get("confidence_pct"),
                "confidence_interval": m.get("confidence_interval"),
                "trend": m.get("trend"),
                "risk": m.get("risk"),
                "kategori": m.get("kategori"),
                "horizon_label": m.get("horizon_label"),
            }
        out["horizons"][str(days)] = slim
    out["last_3_months"] = (primary.get("history") or [])[-3:]
    return out


def _merge_gemini_comments(primary: dict, parsed: dict | list) -> list[str]:
    """Gemini çıktısını forecasts.*.ai_yorum alanlarına yazar."""
    narratives = []
    forecasts = primary.get("forecasts") or {}

    if isinstance(parsed, list):
        # Eski format: düz madde listesi
        for item in parsed:
            text = str(item).strip()
            if text:
                narratives.append(text)
        return narratives[:8]

    if not isinstance(parsed, dict):
        return narratives

    # Beklenen: { "30": { "atik_miktari": "yorum", ... }, ... } veya { "comments": [...] }
    comments_block = parsed.get("comments") or parsed.get("yorumlar") or parsed
    if isinstance(comments_block, list):
        return [str(x).strip() for x in comments_block if str(x).strip()][:8]

    for days_key, metrics in comments_block.items():
        block = forecasts.get(str(days_key))
        if not block or not isinstance(metrics, dict):
            continue
        for key, text in metrics.items():
            if key not in METRIC_KEYS and key != "en_yogun_kategori":
                continue
            target = block.get(key)
            if isinstance(target, dict) and text:
                target["ai_yorum"] = str(text).strip()
                if key == "kategori_artisi" and isinstance(block.get("en_yogun_kategori"), dict):
                    block["en_yogun_kategori"]["ai_yorum"] = target["ai_yorum"]
                if str(days_key) in ("7", "30", "90", "180", "365"):
                    narratives.append(target["ai_yorum"])

    return narratives[:10]


def generate_prediction_report(
    lookback_months: int = 12,
    *,
    il=None,
    ilce=None,
    mahalle=None,
    include_all_lookbacks: bool = True,
) -> dict:
    """
    İstatistiksel tahmin + AI yorum.
    Gemini yalnızca yorum üretir; rakamlar prediction_engine'den gelir.
    """
    from services.demo_manager import (
        is_demo_mode,
        is_prediction_data_sufficient,
        should_use_demo,
        use_demo_ai,
        use_demo_prediction,
    )
    from services import demo_provider

    filters = {"il": il, "ilce": ilce, "mahalle": mahalle}

    # Demo Mode / Demo Prediction açıkken MASTER zorunlu
    if is_demo_mode() or use_demo_prediction():
        return demo_provider.prediction_report(
            lookback_months,
            il=il,
            ilce=ilce,
            mahalle=mahalle,
            include_all_lookbacks=include_all_lookbacks,
        )

    if include_all_lookbacks:
        multi = run_multi_lookback_forecast(**filters)
        primary = multi["primary"]
    else:
        primary = run_statistical_forecast(lookback_months, **filters)
        multi = {
            "lookbacks": {str(lookback_months): primary},
            "primary": primary,
            "horizons_days": list(FORECAST_HORIZONS_DAYS),
            "lookback_options": [lookback_months],
            "metrics": list(METRIC_KEYS),
        }

    if should_use_demo(
        "prediction",
        real_data_sufficient=is_prediction_data_sufficient(primary),
    ):
        return demo_provider.prediction_report(
            lookback_months,
            il=il,
            ilce=ilce,
            mahalle=mahalle,
            include_all_lookbacks=include_all_lookbacks,
        )

    # Önce tüm lookback'lere kural yorumu
    for payload in (multi.get("lookbacks") or {}).values():
        _apply_rule_comments(payload)
    narratives = _apply_rule_comments(primary)
    source = "rules"

    if use_demo_ai():
        return {
            **multi,
            "narratives": narratives,
            "narrative_source": "demo",
        }

    client = get_client()
    if client:
        compact = _compact_for_gemini(primary)
        prompt = (
            "Sen AtıkPort tahmin asistanısın. Aşağıdaki İSTATİSTİKSEL tahmin JSON'unu yorumla.\n"
            "Yeni sayı uydurma; yalnızca verilen predicted / change_pct / confidence_pct / "
            "trend / risk değerlerini kullan.\n"
            "Her ufuk (7,30,90,180,365) ve her metrik "
            "(atik_miktari, kategori_artisi, teslim_orani, katilim, co2) için kısa Türkçe yorum yaz.\n"
            "JSON nesne döndür:\n"
            '{"7":{"atik_miktari":"...","kategori_artisi":"...","teslim_orani":"...","katilim":"...","co2":"..."},'
            '"30":{...},"90":{...},"180":{...},"365":{...}}\n\n'
            f"VERİ:\n{json.dumps(compact, ensure_ascii=False, default=str)}"
        )
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types
                from helpers.json_utils import json_cikar

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                parsed = json_cikar((result.text or "").strip())
                gem_narratives = _merge_gemini_comments(primary, parsed)
                if gem_narratives or (isinstance(parsed, dict) and parsed):
                    # Lookback kopyalarına da primary yorumlarını yansıtma gerekmez;
                    # seçilen lookback primary üzerinden gelir.
                    if gem_narratives:
                        narratives = gem_narratives
                    else:
                        narratives = [
                            m.get("ai_yorum")
                            for d in FORECAST_HORIZONS_DAYS
                            for k in METRIC_KEYS
                            for m in [((primary.get("forecasts") or {}).get(str(d)) or {}).get(k)]
                            if isinstance(m, dict) and m.get("ai_yorum")
                        ][:10]
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Tahmin AI yorumu başarısız (%s): %s", model, exc)

    return {
        **multi,
        "narratives": narratives,
        "narrative_source": source,
    }
