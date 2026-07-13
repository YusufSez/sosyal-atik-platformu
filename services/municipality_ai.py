"""Belediye paneli AI asistanı — Gemini + gelişmiş rule engine (rapor kartları)."""

from __future__ import annotations

import json
import logging
import re

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.municipality_analytics import municipality_analysis_context

logger = logging.getLogger("atikport.municipality_ai")

_PRIORITIES = ("Kritik", "Yüksek", "Orta", "Düşük")


def _card(*, title: str, analysis: str, expected_impact: str, priority: str, trigger: str = "") -> dict:
    return {
        "title": (title or "").strip()[:90],
        "analysis": (analysis or "").strip()[:500],
        "expected_impact": (expected_impact or "").strip()[:200],
        "priority": priority if priority in _PRIORITIES else "Orta",
        "trigger": trigger,
    }


def _priority_from_magnitude(value: float, *, high: float = 25, mid: float = 10) -> str:
    v = abs(float(value or 0))
    if v >= high:
        return "Kritik" if v >= high * 1.5 else "Yüksek"
    if v >= mid:
        return "Orta"
    return "Düşük"


def _advanced_rule_cards(ctx: dict) -> list[dict]:
    """Gelişmiş kural motoru — rapor dili, yapılandırılmış kartlar."""
    cards: list[dict] = []
    dashboard = ctx.get("dashboard") or {}
    deltas = ctx.get("kategori_artisi") or []
    districts = ctx.get("mahalle_yogunlugu") or []
    teslim_orani = float(ctx.get("teslim_orani") or 0)
    katilim = ctx.get("vatandas_katilimi") or {}
    trend30 = ctx.get("trend_30_gun") or {}
    seasonal = ctx.get("mevsimsel") or []

    # 1) Kategori artışı
    for d in sorted(deltas, key=lambda x: -(x.get("degisim_yuzde") or 0))[:3]:
        pct = d.get("degisim_yuzde") or 0
        if abs(pct) < 10:
            continue
        if (d.get("bu_hafta") or 0) + (d.get("onceki_hafta") or 0) <= 0:
            continue
        kat = d["kategori"]
        if pct > 0:
            cards.append(_card(
                title=f"{kat} Kategorisinde Artış",
                analysis=(
                    f"{kat} atıklarında dikkat çekici artış gözlenmiştir. "
                    f"Geçen haftaya göre yaklaşık %{abs(pct):.0f} yükseliş kaydedilmiştir."
                ),
                expected_impact="Toplama kapasitesinin güçlenmesi ve vatandaş bilincinin artması",
                priority=_priority_from_magnitude(pct),
                trigger="kategori_artisi",
            ))
            if pct >= 20:
                cards.append(_card(
                    title="Mobil Toplama Kapasitesinin Artırılması",
                    analysis=(
                        f"{kat} hacmindeki yükseliş nedeniyle mobil toplama noktalarının "
                        "artırılması önerilmektedir."
                    ),
                    expected_impact="Teslim süresi kısalması · erişilebilirlik artışı",
                    priority="Yüksek",
                    trigger="kampanya",
                ))
        else:
            cards.append(_card(
                title=f"{kat} Hacminde Gerileme",
                analysis=(
                    f"{kat} kategorisinde son haftaya göre %{abs(pct):.0f} azalma gözlenmiştir. "
                    "Farkındalık çalışmalarının sürdürülmesi faydalı olacaktır."
                ),
                expected_impact="Katılımın yeniden dengelenmesi",
                priority="Orta",
                trigger="kategori_azalis",
            ))

    # 2) Mahalle yoğunluğu
    if districts:
        top = districts[0]
        cards.append(_card(
            title=f"{top['bolge']} Bölgesinde Yoğunluk",
            analysis=(
                f"{top['bolge']} bölgesinde yoğunluk oluşmuştur. "
                f"Bölgede {top['ilan_sayisi']} ilan ile öne çıkan bir operasyon yükü görülmektedir."
            ),
            expected_impact="Yerel müdahale ve mahalle bazlı bilgilendirme",
            priority="Yüksek" if top["ilan_sayisi"] >= 5 else "Orta",
            trigger="mahalle_yogunlugu",
        ))

    # 3) Teslim oranı
    if teslim_orani >= 60:
        cards.append(_card(
            title="Teslim Performansında İstikrar",
            analysis=(
                f"Teslim oranı %{teslim_orani:.0f} seviyesindedir. "
                "Geri dönüşüm ve paylaşım süreçlerinin tamamlanma eğilimi olumludur."
            ),
            expected_impact="Operasyonel güvenilirliğin korunması",
            priority="Düşük",
            trigger="teslim_orani",
        ))
    elif teslim_orani > 0:
        cards.append(_card(
            title="Teslim Oranının İyileştirilmesi",
            analysis=(
                f"Teslim oranı %{teslim_orani:.0f} düzeyindedir. "
                "Eşleştirme ve mobil toplama süreçlerinin güçlendirilmesi önerilmektedir."
            ),
            expected_impact="Teslim tamamlanma oranında artış",
            priority="Yüksek" if teslim_orani < 35 else "Orta",
            trigger="teslim_orani",
        ))

    # 4) Vatandaş katılımı
    oran = float(katilim.get("oran") or 0)
    if oran >= 20:
        cards.append(_card(
            title="Vatandaş Katılımında Canlılık",
            analysis=(
                f"Günlük vatandaş katılım oranı %{oran:.0f} düzeyindedir "
                f"({katilim.get('gunluk', 0)} aktif kullanıcı). "
                "Katılımın sürdürülebilirliği açısından olumlu bir görünüm söz konusudur."
            ),
            expected_impact="Platform kullanımının devamlılığı",
            priority="Düşük",
            trigger="katilim",
        ))
    else:
        cards.append(_card(
            title="Vatandaş Katılımının Güçlendirilmesi",
            analysis=(
                f"Vatandaş katılım oranı %{oran:.0f} seviyesindedir. "
                "Mahalle bilgilendirme ve teşvik kampanyalarının artırılması önerilmektedir."
            ),
            expected_impact="Aktif kullanıcı sayısında artış",
            priority="Yüksek" if oran < 10 else "Orta",
            trigger="katilim",
        ))

    # 5) Son 30 gün trendi
    ilan_pct = float(trend30.get("ilan_degisim_yuzde") or 0)
    if abs(ilan_pct) >= 8 or (trend30.get("ilan_son") or 0) > 0:
        cards.append(_card(
            title="Son 30 Günlük İlan Trendi",
            analysis=(
                f"Son 30 günlük ilan trendi önceki 30 güne kıyasla "
                f"%{abs(ilan_pct):.0f} oranında {'artış' if ilan_pct >= 0 else 'azalış'} göstermektedir. "
                f"Dönem içinde {trend30.get('ilan_son', 0)} yeni ilan ve "
                f"{trend30.get('teslim_son', 0)} teslim kaydedilmiştir."
            ),
            expected_impact="Operasyon planlamasının güncellenmesi",
            priority=_priority_from_magnitude(ilan_pct, high=30, mid=12),
            trigger="trend_30",
        ))

    # 6) Mevsimsel / dönemsel
    if seasonal:
        top_s = seasonal[0]
        if abs(top_s.get("degisim_yuzde") or 0) >= 15:
            kat = top_s["kategori"]
            pct = top_s["degisim_yuzde"]
            cards.append(_card(
                title=f"{kat} İçin Dönemsel Değişim",
                analysis=(
                    f"{kat} kategorisinde son üç aylık dilimler arasında "
                    f"%{abs(pct):.0f} oranında {'yükseliş' if pct > 0 else 'gerileme'} gözlenmiştir. "
                    "Mevsimsel talep değişimine uygun planlama yapılması önerilmektedir."
                ),
                expected_impact="Dönemsel kapasite ve kampanya planlaması",
                priority=_priority_from_magnitude(pct),
                trigger="mevsimsel",
            ))

    # Geri dönüşüm / genel istikrar
    atik_kg = float(dashboard.get("geri_kazanilan_atik_kg") or 0)
    if atik_kg > 0 and teslim_orani >= 40:
        cards.append(_card(
            title="Geri Dönüşüm Performansı",
            analysis=(
                "Geri dönüşüm oranı son dönemde istikrarlı şekilde yükselme eğilimindedir. "
                f"Toplam {atik_kg:.1f} kg atık geri kazanımı kayda geçmiştir."
            ),
            expected_impact="Sürdürülebilirlik skoruna olumlu katkı",
            priority="Orta",
            trigger="geri_donusum",
        ))

    if not cards:
        cards.append(_card(
            title="Veri Birikimi Süreci",
            analysis=(
                "Seçili bölgede kapsamlı trend üretimi için veri birikimi devam etmektedir. "
                "İlan ve teslim kayıtları çoğaldıkça rapor kalitesi artacaktır."
            ),
            expected_impact="Analiz derinliğinin artması",
            priority="Düşük",
            trigger="bos",
        ))

    # Trigger tekrarsız, en fazla 6 kart
    seen: set[str] = set()
    unique: list[dict] = []
    for c in cards:
        key = f"{c['trigger']}:{c['title']}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique[:6]


def _parse_gemini_cards(text: str) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    match = re.search(r"\[[\s\S]*\]", text)
    payload = match.group(0) if match else text
    try:
        from helpers.json_utils import json_cikar

        data = json_cikar(payload)
    except Exception:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    cards = []
    for item in data[:6]:
        if isinstance(item, str):
            # Eski düz metin fallback
            cards.append(_card(
                title="Operasyon Notu",
                analysis=item,
                expected_impact="Operasyonel farkındalık",
                priority="Orta",
                trigger="gemini",
            ))
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("baslik") or "").strip()
        analysis = str(
            item.get("analysis") or item.get("analiz") or item.get("description") or ""
        ).strip()
        if not title or not analysis:
            continue
        cards.append(_card(
            title=title,
            analysis=analysis,
            expected_impact=str(
                item.get("expected_impact") or item.get("etki") or item.get("beklenen_etki") or ""
            ),
            priority=str(item.get("priority") or item.get("oncelik") or "Orta"),
            trigger=str(item.get("trigger") or "gemini"),
        ))
    return cards


def _gemini_prompt(ctx: dict) -> str:
    slim = {
        "teslim_orani": ctx.get("teslim_orani"),
        "vatandas_katilimi": ctx.get("vatandas_katilimi"),
        "trend_30_gun": ctx.get("trend_30_gun"),
        "kategori_artisi": (ctx.get("kategori_artisi") or [])[:6],
        "mahalle_yogunlugu": (ctx.get("mahalle_yogunlugu") or [])[:5],
        "mevsimsel": (ctx.get("mevsimsel") or [])[:5],
        "dashboard": {
            k: (ctx.get("dashboard") or {}).get(k)
            for k in (
                "toplam_aktif_ilan",
                "toplam_teslim",
                "geri_kazanilan_atik_kg",
                "gunluk_kullanici",
                "ortalama_teslim_gun",
            )
        },
    }
    return (
        "Sen AtıkPort belediye karar destek asistanısın. Resmi rapor dili kullan.\n"
        "Yalnızca geçerli JSON dizi döndür (markdown yok). Her eleman:\n"
        '{"title","analysis","expected_impact","priority","trigger"}\n'
        "priority: Kritik|Yüksek|Orta|Düşük.\n"
        "Analiz alanları: kategori artışı, mahalle yoğunluğu, teslim oranı, "
        "vatandaş katılımı, son 30 gün trendi, mevsimsel değişim.\n"
        "Örnek üslup:\n"
        "- Geri dönüşüm oranı son üç ayda istikrarlı şekilde yükselmektedir.\n"
        "- Elektronik atıklarda dikkat çekici artış gözlenmiştir.\n"
        "- Mobil toplama noktalarının artırılması önerilmektedir.\n"
        "En fazla 5 kart. Tahmin (forecast) üretme; mevcut veriye dayan.\n\n"
        f"VERİ:\n{json.dumps(slim, ensure_ascii=False, default=str)}"
    )


def generate_municipality_insights(il=None, ilce=None, mahalle=None) -> dict:
    """
    Belediye AI analizi.
    Dönüş: insights = yapılandırılmış kart listesi (title/analysis/expected_impact/priority).
    Gemini yoksa gelişmiş rule engine aynı şemayı üretir.
    """
    from services.demo_manager import (
        is_dashboard_data_sufficient,
        is_demo_mode,
        should_use_demo,
        use_demo_ai,
    )
    from services import demo_provider

    ctx = municipality_analysis_context(il=il, ilce=ilce, mahalle=mahalle)
    dashboard = ctx["dashboard"]
    fallback = _advanced_rule_cards(ctx)

    if (
        is_demo_mode()
        or use_demo_ai()
        or should_use_demo(
            "dashboard",
            real_data_sufficient=is_dashboard_data_sufficient(dashboard),
        )
    ):
        demo = demo_provider.municipality_ai_insights(dashboard, il=il)
        return {
            "source": demo["source"],
            "insights": demo["insights"],
            "dashboard": dashboard,
            "context": ctx,
        }

    client = get_client()
    if not client:
        return {
            "source": "rules",
            "insights": fallback,
            "dashboard": dashboard,
            "context": ctx,
        }

    prompt = _gemini_prompt(ctx)
    for model in (FREE_MODEL, FREE_MODEL_BACKUP):
        try:
            from google.genai import types

            result = client.models.generate_content(
                model=model,
                contents=[types.Content(parts=[types.Part(text=prompt)])],
            )
            cards = _parse_gemini_cards(result.text or "")
            if cards:
                return {
                    "source": f"gemini:{model}",
                    "insights": cards,
                    "dashboard": dashboard,
                    "context": ctx,
                }
        except Exception as exc:
            logger.warning("Belediye AI asistanı başarısız (%s): %s", model, exc)
            continue

    return {
        "source": "rules",
        "insights": fallback,
        "dashboard": dashboard,
        "context": ctx,
    }
