"""Tahmin sonuçlarından Gemini / kural tabanlı Türkçe yorum üretimi."""

from __future__ import annotations

import json
import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.prediction_engine import run_multi_lookback_forecast, run_statistical_forecast

logger = logging.getLogger("atikport.prediction_ai")


def _rule_based_narratives(forecast_payload: dict) -> list[str]:
    insights = []
    forecasts = forecast_payload.get("forecasts") or {}
    # 30 günlük pencereyi ana anlatım olarak kullan
    f30 = forecasts.get("30") or {}
    atik = f30.get("atik_miktari") or {}
    kaynak = f30.get("kaynak_paylasimi") or {}
    teslim = f30.get("teslim_orani") or {}
    kategori = f30.get("en_yogun_kategori") or {}

    if atik:
        pct = atik.get("change_pct") or 0
        yon = "artması" if pct >= 0 else "azalması"
        insights.append(
            f"Atık miktarının önümüzdeki 30 günde %{abs(pct):.0f} {yon} beklenmektedir "
            f"(tahmini {atik.get('predicted', 0)} kg)."
        )
    if kaynak:
        pct = kaynak.get("change_pct") or 0
        yon = "artması" if pct >= 0 else "azalması"
        insights.append(
            f"Kaynak paylaşımının gelecek ay %{abs(pct):.0f} {yon} beklenmektedir."
        )
    if kategori.get("en_yogun_kategori"):
        pct = kategori.get("change_pct") or 0
        yon = "artması" if pct >= 0 else "azalması"
        insights.append(
            f"{kategori['en_yogun_kategori']} kategorisinin gelecek ay "
            f"%{abs(pct):.0f} {yon} beklenmektedir."
        )
    if teslim:
        insights.append(
            f"Teslim oranının önümüzdeki 30 günde yaklaşık "
            f"%{teslim.get('predicted', 0):.0f} seviyesinde olması beklenmektedir."
        )

    f7 = forecasts.get("7") or {}
    if f7.get("atik_miktari"):
        insights.append(
            f"Önümüzdeki 7 günde yaklaşık {f7['atik_miktari'].get('predicted', 0)} kg "
            f"atık geri kazanımı öngörülmektedir."
        )
    f90 = forecasts.get("90") or {}
    if f90.get("kaynak_paylasimi"):
        insights.append(
            f"90 günlük görünümde kaynak paylaşımı tahmini "
            f"{f90['kaynak_paylasimi'].get('predicted', 0)} ilandır."
        )

    if not insights:
        insights.append(
            "Yeterli tarihsel veri birikince istatistiksel tahminler burada görünecek."
        )
    return insights[:6]


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
    filters = {"il": il, "ilce": ilce, "mahalle": mahalle}
    if include_all_lookbacks:
        multi = run_multi_lookback_forecast(**filters)
        primary = multi["primary"]
    else:
        primary = run_statistical_forecast(lookback_months, **filters)
        multi = {
            "lookbacks": {str(lookback_months): primary},
            "primary": primary,
            "horizons_days": [7, 30, 90],
            "lookback_options": [lookback_months],
        }

    narratives = _rule_based_narratives(primary)
    source = "rules"

    client = get_client()
    if client:
        compact = {
            "lookback_months": primary.get("lookback_months"),
            "forecasts_30d": (primary.get("forecasts") or {}).get("30"),
            "forecasts_7d": (primary.get("forecasts") or {}).get("7"),
            "forecasts_90d": (primary.get("forecasts") or {}).get("90"),
            "last_3_months": (primary.get("history") or [])[-3:],
        }
        prompt = (
            "Sen AtıkPort tahmin asistanısın. Aşağıdaki İSTATİSTİKSEL tahmin JSON'unu yorumla.\n"
            "Yeni sayı uydurma; yalnızca verilen change_pct / predicted değerlerini kullan.\n"
            "Türkçe, kısa maddeler yaz. Örnek üslup: "
            "'Elektronik atıkların gelecek ay %18 artması beklenmektedir.'\n"
            "En fazla 5 madde. JSON dizi döndür: [\"madde1\", ...]\n\n"
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
                if isinstance(parsed, list) and parsed:
                    narratives = [str(x).strip() for x in parsed if str(x).strip()][:6]
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Tahmin AI yorumu başarısız (%s): %s", model, exc)

    return {
        **multi,
        "narratives": narratives,
        "narrative_source": source,
    }
