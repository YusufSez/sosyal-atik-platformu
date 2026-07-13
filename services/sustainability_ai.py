"""Sustainability Scoring — AI önerileri (vatandaş katılımı / sıfır atık bilinci)."""

from __future__ import annotations

import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.sustainability_scoring import score_region

logger = logging.getLogger("atikport.sustainability_ai")

_FOCUS_CATEGORIES = ("Elektronik", "Bitkisel Yağ", "Plastik", "Organik", "Cam", "Metal")

# Kriter bazlı öneri havuzları — resmi, aksiyon odaklı, 1–2 cümle
_CRITERION_POOLS: dict[str, tuple[str, ...]] = {
    "geri_donusum": (
        "Vatandaşların geri dönüşüme katılımını artırmak amacıyla mahalle bazlı mobil atık toplama günleri düzenlenmesi önerilmektedir. Bu yaklaşım erişilebilirliği yükselterek geri dönüşüm oranına olumlu katkı sağlar.",
        "Mahalle bazlı geri dönüşüm performanslarının kamuoyu ile paylaşılması vatandaş motivasyonunu artırabilir. Şeffaf bilgilendirme, uzun vadede bilinçli katılım kültürünü güçlendirir.",
        "İlkokul ve lise düzeyinde düzenlenecek sıfır atık eğitim programları uzun vadeli geri dönüşüm alışkanlığı kazandıracaktır. Erken yaşta edinilen farkındalık, belediye genelindeki geri dönüşüm performansını destekler.",
        "Yoğun atık oluşan bölgelerde akıllı konteyner ve doluluk takip sistemlerinin yaygınlaştırılması önerilir. Dijital izlenebilirlik, toplama verimliliği ile birlikte vatandaş güvenini artırır.",
    ),
    "teslim": (
        "Teslim sürecini tamamlayan kullanıcıları ödüllendiren puan ve rozet sistemi katılım oranını artırabilir. Somut teşvikler, platformdaki teslim tamamlanma oranını yükseltmeye yardımcı olur.",
        "Atık üretiminin yoğun olduğu mahallelerde belediye mobil uygulaması üzerinden geri dönüşüm bildirimleri gönderilebilir. Zamanında hatırlatmalar, başlatılan süreçlerin teslimle tamamlanmasını kolaylaştırır.",
        "Düşük performans gösteren bölgelerde sosyal medya ve SMS destekli farkındalık kampanyaları uygulanabilir. Hedefli iletişim, vatandaşların ilanlarını sonuçlandırmasını teşvik eder.",
    ),
    "katilim": (
        "Düşük performans gösteren bölgelerde sosyal medya ve SMS destekli farkındalık kampanyaları uygulanabilir. Düzenli bilgilendirme, vatandaş katılımını ve sıfır atık bilincini güçlendirir.",
        "Yerel işletmelerle iş birliği yapılarak geri dönüşüme katılan vatandaşlara teşvik kuponları sunulabilir. Ortak teşvik modeli, gönüllü katılımı sürdürülebilir biçimde artırır.",
        "Mahalle muhtarlıkları ve site yönetimleriyle ortak bilgilendirme toplantıları düzenlenmesi önerilmektedir. Yerel ağlar üzerinden yürütülen çalışmalar, daha geniş vatandaş kesimine ulaşmayı sağlar.",
        "Gönüllü çevre elçileri programı ile mahallelerde akran eğitimi yaygınlaştırılabilir. Topluluk temelli yaklaşım, katılımın sürekliliğine katkı sunar.",
    ),
    "kaynak_paylasimi": (
        "Kurumsal işletmelerin fazla kaynaklarını paylaşabileceği dijital kaynak pazarı kullanımının yaygınlaştırılması önerilmektedir. Bu uygulama, atığa dönüşmeden yeniden kullanımı teşvik ederek döngüsel ekonomiye katkı sağlar.",
        "Okul ve kamu kurumlarında ikinci el eşya paylaşım günleri düzenlenmesi, kaynak paylaşımı kültürünü güçlendirebilir. Kurumsal örnekler, vatandaş davranışına olumlu yansır.",
        "Yerel işletmelerle iş birliği yapılarak fazla stokların dijital ilanlarla paylaşıldığı kampanyalar planlanabilir. Ortak görünürlük, kaynak paylaşımı oranını yükseltmeye yardımcı olur.",
    ),
    "karbon": (
        "Mahalle bazlı geri dönüşüm performanslarının kamuoyu ile paylaşılması vatandaş motivasyonunu artırabilir. Artan katılım, karbon azaltımına dolaylı fakat ölçülebilir katkı sağlar.",
        "Yoğun atık oluşan bölgelerde akıllı konteyner ve doluluk takip sistemlerinin yaygınlaştırılması önerilir. Daha verimli toplama, taşımadan kaynaklanan emisyonların azaltılmasına destek olur.",
        "Kurumsal işletmelerin fazla kaynaklarını paylaşabileceği dijital kaynak pazarı kullanımının yaygınlaştırılması önerilmektedir. Yeniden kullanım, üretim kaynaklı karbon yükünü azaltmaya katkı sunar.",
    ),
    "teslim_suresi": (
        "Teslim sürecini tamamlayan kullanıcıları ödüllendiren puan ve rozet sistemi katılım oranını artırabilir. Hızlı tamamlanan eşleşmeler, bekleme süresini kısaltarak kullanıcı memnuniyetini yükseltir.",
        "Atık üretiminin yoğun olduğu mahallelerde belediye mobil uygulaması üzerinden geri dönüşüm bildirimleri gönderilebilir. Anlık bilgilendirme, eşleştirme ve teslim süreçlerinin hızlanmasına yardımcı olur.",
        "Mahalle bazlı mobil atık toplama günlerinin takvime bağlanması, vatandaşların süreçleri zamanında tamamlamasını kolaylaştırır. Planlı erişim, ortalama teslim süresini iyileştirmeye katkı sağlar.",
    ),
    "ai_dogruluk": (
        "Vatandaşlara ilan oluşturma rehberleri ve örnek fotoğraf standartları sunan dijital bilgilendirme içerikleri hazırlanması önerilmektedir. Daha nitelikli ilanlar, otomatik değerlendirme tutarlılığını artırır.",
        "Okul ve kamu kurumlarında düzenlenecek kısa bilgilendirme oturumlarıyla doğru ilan tanımlama alışkanlığı kazandırılabilir. Standartlaşan içerik kalitesi, platform güvenilirliğini güçlendirir.",
    ),
}

_CATEGORY_POOLS: dict[str, tuple[str, ...]] = {
    "Elektronik": (
        "Elektronik atıkların düzenli toplanabilmesi için okullar ve kamu kurumlarında dönemsel e-atık toplama etkinlikleri düzenlenebilir. Kurumsal erişim, elektronik atık bilincini ve geri kazanım oranını yükseltir.",
        "Elektronik atıkların çevreye ve insan sağlığına etkisini anlatan mahalle bilgilendirme seminerleri planlanabilir. Bilinç artışı, vatandaşların e-atıkları düzenli kanallara yönlendirmesini destekler.",
    ),
    "Bitkisel Yağ": (
        "Bitkisel atık yağların çevreye zarar vermesini önlemek amacıyla apartman ve site yönetimleriyle ortak toplama kampanyaları planlanabilir. Yerel iş birliği, yağların kanalizasyona karışmasını azaltarak geri kazanımı güçlendirir.",
        "Restoran ve kafelerle yürütülecek bitkisel atık yağ geri kazanım protokollerinin yaygınlaştırılması önerilmektedir. Kurumsal ortaklıklar, düzenli toplama alışkanlığını kalıcı hale getirir.",
    ),
    "Plastik": (
        "Plastik atık azaltımını desteklemek üzere okullarda plastik kullanımı farkındalık haftaları düzenlenebilir. Erken yaş eğitimi, uzun vadede plastik geri dönüşüm katılımını artırır.",
        "Mahalle pazarlarında tek kullanımlık plastik yerine yeniden kullanılabilir alternatifleri tanıtan stantlar kurulabilir. Görünür kampanyalar, davranış değişimini hızlandırır.",
    ),
    "Organik": (
        "Organik atıkların kompostlaştırılmasına yönelik mahalle bahçesi ve okul bahçesi projeleri desteklenebilir. Yerel uygulamalar, organik atık bilincini ve geri kazanımı güçlendirir.",
        "Apartman yönetimlerine kompost bilgilendirme kitleri dağıtılarak organik atık ayrıştırma oranı yükseltilebilir. Kolay erişilen rehberler, gönüllü katılımı kolaylaştırır.",
    ),
    "Cam": (
        "Cam ambalajların ayrı toplanmasını teşvik etmek amacıyla site ve okul noktalarında dönemsel cam toplama etkinlikleri düzenlenebilir. Kolay erişim, cam geri dönüşüm katılımını artırır.",
        "Mahalle muhtarlıklarıyla ortak cam geri dönüşüm bilgilendirme afişleri yaygınlaştırılabilir. Yerel görünürlük, doğru ayrıştırma alışkanlığını destekler.",
    ),
    "Metal": (
        "Metal ambalaj geri dönüşümünü artırmak için yerel işletmeler ve okullarla ortak toplama kutuları yerleştirilebilir. Ortak altyapı, vatandaş katılımını pratik hale getirir.",
        "Metal atıkların ekonomik değerini anlatan kısa dijital bilgilendirme içerikleri paylaşılabilir. Farkındalık artışı, ayrıştırılmış metal teslimlerini teşvik eder.",
    ),
}

_DEFAULT_POOL = (
    "Mahalle bazlı geri dönüşüm performanslarının kamuoyu ile paylaşılması vatandaş motivasyonunu artırabilir. Şeffaf iletişim, sıfır atık bilincinin yaygınlaşmasına katkı sağlar.",
    "İlkokul ve lise düzeyinde düzenlenecek sıfır atık eğitim programları uzun vadeli geri dönüşüm alışkanlığı kazandıracaktır. Eğitim temelli yaklaşım, sürdürülebilir katılımın temelini oluşturur.",
    "Yerel işletmelerle iş birliği yapılarak geri dönüşüme katılan vatandaşlara teşvik kuponları sunulabilir. Ortak teşvikler, gönüllü katılımı güçlendirir.",
)


def _pick(pool: tuple[str, ...] | list[str], salt: int, offset: int = 0) -> str:
    if not pool:
        return _DEFAULT_POOL[0]
    return pool[(salt + offset) % len(pool)]


def _rule_suggestions(scored: dict) -> list[str]:
    """Kural tabanlı öneriler — Gemini ile aynı üslup (bakanlık / vatandaş katılımı)."""
    criteria = sorted(scored.get("criteria") or [], key=lambda c: c["score"])
    metrics = scored.get("metrics") or {}
    shares = metrics.get("kategori_paylari") or {}
    puan = int(round(float(scored.get("puan") or 0)))
    salt = puan + int(metrics.get("teslim") or 0) + int(metrics.get("atik_teslim") or 0)

    tips: list[str] = []

    # Zayıf kriterlere göre çeşitlendirilmiş öneriler
    for i, c in enumerate(criteria[:3]):
        if c["score"] >= 75:
            continue
        pool = _CRITERION_POOLS.get(c["key"]) or _DEFAULT_POOL
        tips.append(_pick(pool, salt, i))

    # Kategori paylarına göre (düşük pay = farkındalık ihtiyacı)
    elektronik = float(shares.get("Elektronik", 0) or 0)
    yag = float(shares.get("Bitkisel Yağ", 0) or 0)
    if elektronik < 10:
        tips.append(_pick(_CATEGORY_POOLS["Elektronik"], salt, 3))
    if yag < 8:
        tips.append(_pick(_CATEGORY_POOLS["Bitkisel Yağ"], salt, 4))

    if shares:
        weakest = min(_FOCUS_CATEGORIES, key=lambda k: float(shares.get(k, 0) or 0))
        if weakest not in ("Elektronik", "Bitkisel Yağ") and float(shares.get(weakest, 0) or 0) < 12:
            tips.append(_pick(_CATEGORY_POOLS[weakest], salt, 5))
    else:
        # Veri azsa da çeşitlilik için temel farkındalık önerileri
        tips.append(_pick(_CATEGORY_POOLS["Elektronik"], salt, 6))
        tips.append(_pick(_CATEGORY_POOLS["Bitkisel Yağ"], salt, 7))

    # Genel güçlendirme (yüksek puanlı bölgeler için de anlamlı kalsın)
    if puan >= 80 and len(tips) < 3:
        tips.append(_pick(_DEFAULT_POOL, salt, 8))

    seen: set[str] = set()
    unique: list[str] = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:5] or [_pick(_DEFAULT_POOL, salt, 0)]


def _build_gemini_prompt(scored: dict) -> str:
    weak = ", ".join(
        f"{c['label']}={c['score']}"
        for c in sorted(scored.get("criteria") or [], key=lambda x: x["score"])[:3]
    )
    metrics = scored.get("metrics") or {}
    shares = metrics.get("kategori_paylari") or {}
    share_txt = ", ".join(f"{k}:{v}%" for k, v in sorted(shares.items())) or "veri yok"
    return (
        "Sen AtıkPort için bakanlık seviyesinde sürdürülebilirlik danışmanısın.\n"
        "Türkçe, resmi, profesyonel ve aksiyon odaklı 3 öneri yaz.\n"
        "Odak: vatandaş farkındalığı, eğitim, kampanya, ödüllendirme, okul projeleri, "
        "mobil atık toplama, mahalle çalışmaları, kurum iş birlikleri, dijital bilgilendirme, "
        "gönüllü katılımı ve sıfır atık bilinci.\n"
        "Her öneri 1–2 cümle olsun; neden ve beklenen faydayı içersin.\n"
        "Kısa emir cümleleri yazma (ör. 'Teslim oranını artırın' yasak).\n"
        "Örnek üslup:\n"
        "- Vatandaşların geri dönüşüme katılımını artırmak amacıyla mahalle bazlı mobil atık "
        "toplama günleri düzenlenmesi önerilmektedir.\n"
        "- Teslim sürecini tamamlayan kullanıcıları ödüllendiren puan ve rozet sistemi "
        "katılım oranını artırabilir.\n"
        "- Bitkisel atık yağların çevreye zarar vermesini önlemek amacıyla apartman ve site "
        "yönetimleriyle ortak toplama kampanyaları planlanabilir.\n"
        "- Elektronik atıkların düzenli toplanabilmesi için okullar ve kamu kurumlarında "
        "dönemsel e-atık toplama etkinlikleri düzenlenebilir.\n"
        f"Belediye puanı: {scored.get('puan')} ({scored.get('grade')}). "
        f"Zayıf kriterler: {weak}. "
        f"Kategori payları: {share_txt}.\n"
        "Her satırda bir öneri; numara veya madde işareti kullanma. "
        "Aynı öneriyi tekrar etme."
    )


def generate_sustainability_suggestions(
    *,
    il: str | None = None,
    ilce: str | None = None,
    scored: dict | None = None,
) -> dict:
    scored = scored or score_region(il=il, ilce=ilce)
    rules = _rule_suggestions(scored)
    source = "rules"
    suggestions = list(rules)

    client = get_client()
    if client:
        prompt = _build_gemini_prompt(scored)
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                text = (result.text or "").strip()
                lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
                lines = [ln for ln in lines if len(ln) > 20][:5]
                if lines:
                    suggestions = lines
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Sustainability AI önerisi başarısız (%s): %s", model, exc)

    return {
        "suggestions": suggestions,
        "source": source,
        "puan": scored.get("puan"),
        "grade": scored.get("grade"),
    }
