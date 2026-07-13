"""Sustainability Scoring — yapılandırılmış AI öneri kartları."""

from __future__ import annotations

import json
import logging
import re

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.sustainability_scoring import score_region

logger = logging.getLogger("atikport.sustainability_ai")

_PRIORITIES = ("Kritik", "Yüksek", "Orta", "Düşük")
_DURATIONS = ("Kısa", "Orta", "Uzun")


def _card(
    *,
    title: str,
    description: str,
    expected_impact: str,
    priority: str,
    duration: str,
    reason: str,
    trigger: str,
) -> dict:
    return {
        "title": title.strip()[:80],
        "description": description.strip()[:420],
        "expected_impact": expected_impact.strip()[:160],
        "priority": priority if priority in _PRIORITIES else "Orta",
        "duration": duration if duration in _DURATIONS else "Orta",
        "reason": reason.strip()[:200],
        "trigger": trigger,
    }


def _priority_for_score(score: float) -> str:
    if score < 30:
        return "Kritik"
    if score < 50:
        return "Yüksek"
    if score < 70:
        return "Orta"
    return "Düşük"


# Veriye bağlı öneri şablonları (neden = trigger)
_TEMPLATES: dict[str, dict] = {
    "teslim": {
        "title": "Mahalle Bazlı Mobil Atık Toplama",
        "description": (
            "Atık teslim oranının düşük olduğu mahallelerde haftalık mobil toplama noktaları "
            "oluşturulması önerilmektedir. Muhtarlıklar ve site yönetimleri ile yapılacak iş "
            "birlikleri vatandaş katılımını artıracaktır."
        ),
        "expected_impact": "Teslim oranında artış · Vatandaş katılımında artış",
        "duration": "Kısa",
        "reason_fmt": "Teslim oranı skoru {score:.0f}/100 — lojistik erişim öncelikli.",
    },
    "geri_donusum": {
        "title": "Vatandaş Bilinci ve Sıfır Atık Eğitimi",
        "description": (
            "Geri dönüşüm oranını yükseltmek için mahalle ve okul bazlı sıfır atık eğitim "
            "programlarının yaygınlaştırılması önerilmektedir. Erken farkındalık, uzun vadeli "
            "ayrıştırma alışkanlığı kazandırır."
        ),
        "expected_impact": "Geri dönüşüm oranında artış · Bilinç düzeyinde iyileşme",
        "duration": "Orta",
        "reason_fmt": "Geri dönüşüm skoru {score:.0f}/100 — vatandaş bilinci odaklı müdahale.",
    },
    "katilim": {
        "title": "Puan ve Rozet ile Katılım Teşviki",
        "description": (
            "Teslim sürecini tamamlayan kullanıcıları ödüllendiren puan ve rozet sisteminin "
            "aktif tanıtımı önerilmektedir. Somut teşvikler gönüllü katılımı sürdürülebilir "
            "biçimde artırabilir."
        ),
        "expected_impact": "Aktif kullanıcı oranında artış · Tekrar katılımda artış",
        "duration": "Kısa",
        "reason_fmt": "Vatandaş katılımı skoru {score:.0f}/100 — teşvik mekanizması önerilir.",
    },
    "kaynak_paylasimi": {
        "title": "Kurum İş Birlikleri ve Kaynak Pazarı",
        "description": (
            "Kurumsal işletmelerin fazla kaynaklarını paylaşabileceği dijital kaynak pazarının "
            "yaygınlaştırılması önerilmektedir. Okul ve kamu kurumlarıyla ortak paylaşım günleri "
            "döngüsel kullanımı güçlendirir."
        ),
        "expected_impact": "Kaynak paylaşımında artış · Atığa dönüşmeden yeniden kullanım",
        "duration": "Orta",
        "reason_fmt": "Kaynak paylaşımı skoru {score:.0f}/100 — kurum iş birliği öncelikli.",
    },
    "karbon": {
        "title": "Toplama Rotası ve Lojistik Optimizasyonu",
        "description": (
            "Karbon azaltım performansını güçlendirmek için yoğun mahallelerde toplama rota "
            "optimizasyonu ve akıllı doluluk takibinin yaygınlaştırılması önerilir. Verimli "
            "lojistik, taşımadan kaynaklanan emisyonu düşürür."
        ),
        "expected_impact": "Karbon azaltımında artış · Toplama verimliliğinde iyileşme",
        "duration": "Orta",
        "reason_fmt": "Karbon azaltımı skoru {score:.0f}/100 — rota optimizasyonu önerilir.",
    },
    "teslim_suresi": {
        "title": "Dijital Bildirim ve Hızlı Eşleştirme",
        "description": (
            "Ortalama teslim süresini kısaltmak için mobil uygulama üzerinden zamanında "
            "hatırlatmalar ve mahalle bazlı mobil toplama takviminin duyurulması önerilmektedir."
        ),
        "expected_impact": "Ortalama teslim süresinde azalma · Kullanıcı memnuniyetinde artış",
        "duration": "Kısa",
        "reason_fmt": "Teslim süresi skoru {score:.0f}/100 — süreç hızlandırma odaklı.",
    },
    "ai_dogruluk": {
        "title": "Manuel Doğrulama ve İlan Kalite Rehberi",
        "description": (
            "AI doğruluk oranını yükseltmek için düşük güvenli ilanlarda manuel doğrulama "
            "sürecinin güçlendirilmesi ve vatandaşlara örnek fotoğraf/açıklama rehberlerinin "
            "sunulması önerilmektedir."
        ),
        "expected_impact": "Moderasyon tutarlılığında artış · İlan kalitesinde iyileşme",
        "duration": "Kısa",
        "reason_fmt": "AI doğruluk skoru {score:.0f}/100 — manuel doğrulama desteği önerilir.",
    },
    "elektronik": {
        "title": "Dönemsel E-Atık Toplama Etkinlikleri",
        "description": (
            "Elektronik atıkların düzenli toplanabilmesi için okullar ve kamu kurumlarında "
            "dönemsel e-atık toplama etkinlikleri düzenlenebilir. Kurumsal erişim, e-atık "
            "bilincini güçlendirir."
        ),
        "expected_impact": "Elektronik atık toplama payında artış",
        "duration": "Orta",
        "reason_fmt": "Elektronik kategori payı %{share:.0f} — e-atık kampanyası önerilir.",
    },
    "bitkisel_yag": {
        "title": "Apartman ve Site Yağ Toplama Kampanyası",
        "description": (
            "Bitkisel atık yağların çevreye zarar vermesini önlemek amacıyla apartman ve site "
            "yönetimleriyle ortak toplama kampanyaları planlanabilir."
        ),
        "expected_impact": "Bitkisel yağ geri kazanımında artış · Çevre riskinde azalma",
        "duration": "Kısa",
        "reason_fmt": "Bitkisel yağ kategori payı %{share:.0f} — apartman toplama önerilir.",
    },
    "plastik": {
        "title": "Plastik Azaltımı Farkındalık Kampanyası",
        "description": (
            "Plastik atık yoğunluğunun yüksek olduğu bölgelerde okul ve mahalle pazarlarında "
            "plastik azaltımı farkındalık kampanyaları düzenlenmesi önerilmektedir."
        ),
        "expected_impact": "Plastik atık payında azalma · Yeniden kullanılabilir alternatiflerde artış",
        "duration": "Orta",
        "reason_fmt": "Plastik kategori payı %{share:.0f} — plastik azaltımı önerilir.",
    },
}


def _from_template(key: str, *, score: float = 0, share: float = 0) -> dict:
    t = _TEMPLATES[key]
    return _card(
        title=t["title"],
        description=t["description"],
        expected_impact=t["expected_impact"],
        priority=_priority_for_score(score if key in (
            "teslim", "geri_donusum", "katilim", "kaynak_paylasimi",
            "karbon", "teslim_suresi", "ai_dogruluk",
        ) else max(0, 40 - share)),
        duration=t["duration"],
        reason=t["reason_fmt"].format(score=score, share=share),
        trigger=key,
    )


def _rule_suggestions(scored: dict) -> list[dict]:
    """Metriklere bağlı yapılandırılmış öneri kartları."""
    raw = scored.get("raw") or {}
    metrics = scored.get("metrics") or {}
    shares = metrics.get("kategori_paylari") or {}
    cards: list[dict] = []

    # Zayıf kriterler (skor < 70, missing değilse veya skor düşükse)
    missing = scored.get("missing") or {}
    weak = sorted(
        (
            (k, float(raw.get(k) or 0))
            for k in (
                "teslim", "geri_donusum", "katilim", "kaynak_paylasimi",
                "karbon", "teslim_suresi", "ai_dogruluk",
            )
            if float(raw.get(k) or 0) < 70 and not missing.get(k)
        ),
        key=lambda x: x[1],
    )
    # Missing ama nötr olanlar da iyileştirme fırsatı olabilir — sadece gerçekten düşük olanlar
    for key, score in weak[:3]:
        cards.append(_from_template(key, score=score))

    elektronik = float(shares.get("Elektronik", 0) or 0)
    yag = float(shares.get("Bitkisel Yağ", 0) or 0)
    plastik = float(shares.get("Plastik", 0) or 0)

    if elektronik < 10:
        cards.append(_from_template("elektronik", share=elektronik))
    if yag < 8:
        cards.append(_from_template("bitkisel_yag", share=yag))
    if plastik >= 35:
        cards.append(_from_template("plastik", share=plastik))

    # Yeterli kart yoksa en zayıf kritere göre doldur
    if not cards:
        weakest = min(raw.items(), key=lambda kv: kv[1]) if raw else ("geri_donusum", 45)
        cards.append(_from_template(weakest[0] if weakest[0] in _TEMPLATES else "geri_donusum", score=weakest[1]))

    # Tekrarlayan trigger'ları temizle
    seen: set[str] = set()
    unique: list[dict] = []
    for c in cards:
        if c["trigger"] in seen:
            continue
        seen.add(c["trigger"])
        unique.append(c)
    return unique[:4]


def _parse_gemini_cards(text: str) -> list[dict]:
    """Gemini çıktısından kart listesi çıkar."""
    text = (text or "").strip()
    if not text:
        return []
    # JSON bloğunu yakala
    match = re.search(r"\[[\s\S]*\]", text)
    payload = match.group(0) if match else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    cards = []
    for item in data[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not title or not desc:
            continue
        cards.append(_card(
            title=title,
            description=desc,
            expected_impact=str(item.get("expected_impact") or item.get("etki") or "Performans iyileşmesi"),
            priority=str(item.get("priority") or item.get("oncelik") or "Orta"),
            duration=str(item.get("duration") or item.get("sure") or "Orta"),
            reason=str(item.get("reason") or item.get("neden") or "Veri analizi"),
            trigger=str(item.get("trigger") or "gemini"),
        ))
    return cards


def _build_gemini_prompt(scored: dict) -> str:
    metrics = scored.get("metrics") or {}
    raw = scored.get("raw") or {}
    shares = metrics.get("kategori_paylari") or {}
    return (
        "Sen AtıkPort için bakanlık seviyesinde sürdürülebilirlik karar destek asistanısın.\n"
        "Yalnızca geçerli bir JSON dizi döndür (markdown yok). Her eleman şu alanlara sahip olsun:\n"
        '{"title","description","expected_impact","priority","duration","reason","trigger"}\n'
        "priority: Kritik|Yüksek|Orta|Düşük. duration: Kısa|Orta|Uzun.\n"
        "title tek satır, description 2-3 kısa cümle (max ~60 kelime), expected_impact tek satır.\n"
        "Kısa emir cümlesi yazma. Veriye bağlı 3 kart üret; aynı öneriyi tekrar etme.\n"
        "Eşleme: teslim düşük→lojistik/mobil toplama; geri dönüşüm düşük→bilinç/eğitim; "
        "katılım düşük→puan/rozet; kaynak paylaşımı düşük→kurum iş birliği; "
        "karbon düşük→rota optimizasyonu; AI doğruluk düşük→manuel doğrulama; "
        "elektronik düşük→e-atık; bitkisel yağ düşük→apartman toplama; plastik yüksek→plastik azaltımı.\n"
        f"Puan: {scored.get('puan')} ({scored.get('grade')}). "
        f"Kriter skorları: {json.dumps(raw, ensure_ascii=False)}. "
        f"Metrikler: teslim={metrics.get('teslim')}, atik_teslim={metrics.get('atik_teslim')}, "
        f"teslim_orani={metrics.get('teslim_orani')}, kategori_paylari={json.dumps(shares, ensure_ascii=False)}."
    )


def suggestion_cards_as_text(cards: list) -> list[str]:
    """PDF / geriye dönük metin görünümü."""
    lines = []
    for c in cards or []:
        if isinstance(c, str):
            lines.append(c)
            continue
        lines.append(
            f"{c.get('title', '')}: {c.get('description', '')} "
            f"(Etki: {c.get('expected_impact', '')}; Öncelik: {c.get('priority', '')}; "
            f"Süre: {c.get('duration', '')})"
        )
    return lines


def _rule_ai_report(scored: dict) -> dict:
    """3 güçlü · 3 geliştirme · 3 öneri · beklenen kazanım."""
    criteria = sorted(
        scored.get("criteria") or [],
        key=lambda c: float(c.get("score") or 0),
        reverse=True,
    )
    raw = scored.get("raw") or {}
    metrics = scored.get("metrics") or {}

    strengths = []
    for c in criteria:
        if float(c.get("score") or 0) >= 60 and not c.get("missing_data"):
            strengths.append(
                f"{c['label']}: {c['score']}/100 — göreli güçlü performans."
            )
        if len(strengths) >= 3:
            break
    while len(strengths) < 3:
        if criteria:
            c = criteria[len(strengths) % len(criteria)]
            strengths.append(
                f"{c.get('label')}: mevcut seviye {c.get('score')}/100 ile izleniyor."
            )
        else:
            strengths.append("Veri biriktikçe güçlü yönler netleşecektir.")

    weak = sorted(
        scored.get("criteria") or [],
        key=lambda c: float(c.get("score") or 0),
    )
    improvements = []
    for c in weak:
        if float(c.get("score") or 0) < 70:
            improvements.append(
                f"{c['label']}: {c['score']}/100 — öncelikli geliştirme alanı."
            )
        if len(improvements) >= 3:
            break
    while len(improvements) < 3:
        improvements.append("Eksik veri alanlarının tamamlanması performans görünürlüğünü artırır.")

    # Öneriler: zayıf kriter şablonlarından
    suggestions = _rule_suggestions(scored)
    recommendations = []
    for s in suggestions[:3]:
        recommendations.append(
            f"{s.get('title')}: {s.get('description', '')[:180]}"
        )
    while len(recommendations) < 3:
        recommendations.append(
            "Mahalle bazlı mobil toplama ve vatandaş bilinci kampanyaları önerilir."
        )

    # Beklenen kazanım
    weak_avg = (
        sum(float(c.get("score") or 0) for c in weak[:3]) / max(len(weak[:3]), 1)
        if weak else 45
    )
    lift = max(3.0, round((70 - weak_avg) * 0.25, 1)) if weak_avg < 70 else 2.0
    expected = (
        f"Önerilen 3 aksiyonun uygulanmasıyla genel skorda yaklaşık +{lift} puan, "
        f"teslim oranında %{max(2, int(lift))} ve CO₂ tasarrufunda ölçülebilir artış beklenir. "
        f"Mevcut puan {scored.get('puan')} ({scored.get('grade')})."
    )

    summary = (
        f"Genel değerlendirme: {scored.get('puan')}/100 ({scored.get('grade')}). "
        f"Teslim oranı %{metrics.get('teslim_orani', '—')}, "
        f"katılım %{metrics.get('katilim_orani', '—')}."
    )

    return {
        "summary": summary,
        "strengths": strengths[:3],
        "improvements": improvements[:3],
        "recommendations": recommendations[:3],
        "expected_gains": expected,
        "source": "rules",
    }


def _parse_gemini_report(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    match = re.search(r"\{[\s\S]*\}", text)
    payload = match.group(0) if match else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    def _list3(key_aliases):
        for k in key_aliases:
            val = data.get(k)
            if isinstance(val, list) and val:
                return [str(x).strip() for x in val if str(x).strip()][:3]
        return []

    strengths = _list3(("strengths", "guclu_yonler", "güçlü_yönler"))
    improvements = _list3(("improvements", "gelistirme", "geliştirme_alanlari"))
    recommendations = _list3(("recommendations", "oneriler", "öneriler"))
    expected = str(
        data.get("expected_gains")
        or data.get("beklenen_kazanim")
        or data.get("expected_impact")
        or ""
    ).strip()
    summary = str(data.get("summary") or data.get("ozet") or "").strip()
    if not (strengths and improvements and recommendations and expected):
        return None
    while len(strengths) < 3:
        strengths.append("Veri destekli güçlü yön izleniyor.")
    while len(improvements) < 3:
        improvements.append("Geliştirme alanı veri birikimiyle netleşecek.")
    while len(recommendations) < 3:
        recommendations.append("Operasyonel iyileştirme önerilir.")
    return {
        "summary": summary or "AI sürdürülebilirlik değerlendirmesi.",
        "strengths": strengths[:3],
        "improvements": improvements[:3],
        "recommendations": recommendations[:3],
        "expected_gains": expected[:500],
    }


def generate_sustainability_suggestions(
    *,
    il: str | None = None,
    ilce: str | None = None,
    scored: dict | None = None,
) -> dict:
    scored = scored or score_region(il=il, ilce=ilce)
    rules = _rule_suggestions(scored)
    report = _rule_ai_report(scored)
    source = "rules"
    suggestions = list(rules)

    client = get_client()
    if client:
        report_prompt = (
            "Sen AtıkPort sürdürülebilirlik değerlendirme asistanısın.\n"
            "Yalnızca JSON nesne döndür (markdown yok):\n"
            '{"summary":"...","strengths":["...","...","..."],'
            '"improvements":["...","...","..."],'
            '"recommendations":["...","...","..."],'
            '"expected_gains":"..."}\n'
            "Her listede tam 3 madde. Sayı uydurma; verilen skorları kullan.\n"
            f"Puan: {scored.get('puan')} ({scored.get('grade')}). "
            f"Kriterler: {json.dumps(scored.get('raw') or {}, ensure_ascii=False)}. "
            f"Metrikler: {json.dumps({k: (scored.get('metrics') or {}).get(k) for k in ('teslim_orani','katilim_orani','co2e_kg','geri_donusum_orani')}, ensure_ascii=False)}."
        )
        card_prompt = _build_gemini_prompt(scored)
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=report_prompt)])],
                )
                parsed = _parse_gemini_report(result.text or "")
                if parsed:
                    report = {**parsed, "source": f"gemini:{model}"}
                    source = f"gemini:{model}"

                result2 = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=card_prompt)])],
                )
                cards = _parse_gemini_cards(result2.text or "")
                if cards:
                    suggestions = cards
                    source = f"gemini:{model}"
                if parsed or cards:
                    break
            except Exception as exc:
                logger.warning("Sustainability AI önerisi başarısız (%s): %s", model, exc)

    report["source"] = report.get("source") or source

    return {
        "suggestions": suggestions,
        "report": report,
        "evaluation": report,  # alias
        "source": source,
        "puan": scored.get("puan"),
        "grade": scored.get("grade"),
    }
