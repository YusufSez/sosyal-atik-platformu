"""Belediye paneli için Gemini tabanlı analitik asistan."""

from __future__ import annotations

import json
import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.municipality_analytics import (
    district_density_summary,
    municipality_dashboard,
    weekly_category_deltas,
)

logger = logging.getLogger("atikport.municipality_ai")


def _rule_based_insights(dashboard: dict, deltas: list[dict], districts: list[dict]) -> list[str]:
    """Gemini yokken deterministic içgörüler (test/offline)."""
    insights = []
    for d in deltas:
        pct = d.get("degisim_yuzde") or 0
        if abs(pct) >= 10 and (d.get("bu_hafta") or 0) + (d.get("onceki_hafta") or 0) > 0:
            yon = "artmıştır" if pct > 0 else "azalmıştır"
            insights.append(
                f"Bu hafta {d['kategori'].lower()} atık %{abs(pct):.0f} {yon}."
            )
    if districts:
        top = districts[0]
        insights.append(
            f"{top['bolge']} bölgesinde ilan yoğunluğu öne çıkıyor "
            f"({top['ilan_sayisi']} ilan)."
        )
    if dashboard.get("geri_kazanilan_atik_kg", 0) > 0:
        insights.append(
            f"Toplam {dashboard['geri_kazanilan_atik_kg']:.1f} kg atık geri kazanılmıştır."
        )
    if dashboard.get("toplam_aktif_ilan", 0) == 0:
        insights.append("Seçili bölgede henüz aktif ilan bulunmuyor.")
    if not insights:
        insights.append("Yeterli veri birikince bölgesel trend analizleri burada görünecek.")
    return insights[:6]


def generate_municipality_insights(il=None, ilce=None, mahalle=None) -> dict:
    """
    Dashboard verisini analiz eder; Gemini varsa AI, yoksa kural tabanlı çıktı.
    Tahmin üretmez — yalnızca mevcut veri analizi.
    """
    dashboard = municipality_dashboard(il=il, ilce=ilce, mahalle=mahalle)
    deltas = weekly_category_deltas(il=il)
    districts = district_density_summary(il=il)
    fallback = _rule_based_insights(dashboard, deltas, districts)

    client = get_client()
    if not client:
        return {
            "source": "rules",
            "insights": fallback,
            "dashboard": dashboard,
        }

    payload = {
        "dashboard": dashboard,
        "kategori_degisimleri": deltas,
        "ilce_yogunluk": districts[:8],
    }
    prompt = (
        "Sen AtıkPort belediye analitik asistanısın. Aşağıdaki JSON verisini incele.\n"
        "Sadece mevcut veriye dayalı kısa Türkçe maddeler üret (tahmin/forecast yok).\n"
        "Örnek üslup: 'Bu hafta elektronik atık %22 artmıştır.'\n"
        "En fazla 5 madde. Her madde tek cümle. JSON dizi olarak döndür: "
        '["madde1", "madde2"]\n\n'
        f"VERİ:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )

    for model in (FREE_MODEL, FREE_MODEL_BACKUP):
        try:
            from google.genai import types

            result = client.models.generate_content(
                model=model,
                contents=[types.Content(parts=[types.Part(text=prompt)])],
            )
            text = (result.text or "").strip()
            from helpers.json_utils import json_cikar

            parsed = json_cikar(text)
            if isinstance(parsed, list) and parsed:
                insights = [str(x).strip() for x in parsed if str(x).strip()][:6]
                if insights:
                    return {
                        "source": f"gemini:{model}",
                        "insights": insights,
                        "dashboard": dashboard,
                    }
        except Exception as exc:
            logger.warning("Belediye AI asistanı başarısız (%s): %s", model, exc)
            continue

    return {
        "source": "rules",
        "insights": fallback,
        "dashboard": dashboard,
    }
