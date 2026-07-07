# PRD — Çevresel Etki Paneli

**Ürün:** AtıkPort  
**Modül:** Çevresel Etki Paneli (Environmental Impact Dashboard)  
**Versiyon:** 1.0  
**Tarih:** 6 Temmuz 2026  
**Durum:** Taslak — geliştirmeye hazır  
**Hazırlayan:** AtıkPort ekibi

---

## 1. Özet

### 1.1 Problem
AtıkPort kullanıcıları kaynak paylaşımı ve atık yönlendirmesi yapıyor; ancak platform bugün yalnızca **sayısal ilan istatistikleri** (kullanıcı, ilan, teslim adedi) sunuyor. Kullanıcı ve hakem/jüri için **ölçülebilir çevresel katkı** görünür değil. Bu durum:
- Kullanıcı motivasyonunu düşürür (gamification eksikliği),
- Teknofest / sıfır atık yarışmasında “toplumsal ve sürdürülebilir etki” kriterlerinde zayıf kalır,
- Belediye ve kurum ortaklığı anlatısını desteklemez.

### 1.2 Çözüm
Platformdaki **teslim edilmiş** kaynak ve atık ilanlarından, kategori bazlı katsayılarla **tahmini çevresel etki metrikleri** hesaplayan ve bunları üç seviyede gösteren bir panel:

| Seviye | Hedef kitle | Konum |
|--------|-------------|-------|
| **Genel** | Ziyaretçi, misafir | Anasayfa özet kartları |
| **Kişisel** | Giriş yapmış kullanıcı | Profil + `/etki-panelim` |
| **Yönetim** | Admin | Admin paneli sekmesi |

### 1.3 Başarı kriterleri (MVP)
- Teslim edilen her ilan için otomatik etki kaydı oluşur.
- Anasayfada en az 4 çevresel metrik görünür (CO₂e, su, atık yönlendirme, yeniden kullanım).
- Kullanıcı kendi toplam katkısını profilinde görür.
- Admin şehir/kategori kırılımını görebilir.
- Tüm hesaplamalar şeffaf “tahmini değer” olarak etiketlenir; metodoloji sayfası mevcuttur.

---

## 2. Hedefler ve Kapsam Dışı

### 2.1 İş hedefleri
1. **Yarışma sunumu:** Ölçülebilir sürdürülebilirlik hikâyesi (SDG 12 uyumu).
2. **Kullanıcı tutma:** Teslim sonrası somut geri bildirim → tekrar paylaşım.
3. **Güven:** Şeffaf, kaynak gösterimli hesaplama metodolojisi.
4. **Ölçeklenebilirlik:** İleride belediye raporlama API’sine açılabilir yapı.

### 2.2 Kullanıcı hedefleri
- “Ne kadar fark yarattım?” sorusuna anında cevap.
- Paylaşım sonrası rozet / özet kartı ile paylaşılabilir görsel.
- Atık vs kaynak etkisini ayrı ayrı anlama.

### 2.3 Kapsam dışı (v1)
- Gerçek zamanlı IoT tartı verisi entegrasyonu
- Blockchain tabanlı etki sertifikası
- Üçüncü taraf karbon kredisi satın alma
- Bilimsel düzeyde LCA (Life Cycle Assessment) — v1’de **basitleştirilmiş katsayı modeli** kullanılır
- Alıcı tarafı etki paylaşımı (v2’de değerlendirilebilir)

---

## 3. Kullanıcı Personaları

| Persona | İhtiyaç | Panel kullanımı |
|---------|---------|-----------------|
| **Ayşe (18, lise)** | İlk paylaşımını yaptı, etkisini görmek istiyor | Profil özeti, yeşil puan |
| **Mehmet (35, belediye gönüllüsü)** | Bölgesel etki raporu | Admin kırılımı |
| **Jüri / hakem** | Ölçülebilir etki kanıtı | Anasayfa + metodoloji sayfası |
| **Misafir ziyaretçi** | Platformun değer önerisi | Anasayfa topluluk metrikleri |

---

## 4. Mevcut Durum (As-Is)

### 4.1 İlgili veri modeli
```
User
  ├── guven_puani (teslimde +1)
  ├── il, ilce, latitude, longitude
  └── kaynaklar / atiklar

Kaynak / Atik
  ├── kategori (sabit listeler: constants.py)
  ├── ilan_durumu: Aktif | Rezerve | Teslim Edildi
  ├── user_id, tarih
  └── konum (lat/lng)
```

### 4.2 Mevcut tetikleyici
`blueprints/ilan.py` → `ilan_durum_guncelle`: `ilan_durumu == "Teslim Edildi"` olduğunda `guven_puani += 1`.

### 4.3 Mevcut istatistikler (`main.py`)
- `kullanici`, `kaynak`, `atik`, `teslim` sayıları — çevresel metrik yok.

### 4.4 Eksikler
- Etki hesaplama servisi yok
- Etki kayıt tablosu yok
- Teslim anında etki snapshot’ı yok
- Metodoloji / şeffaflık sayfası yok

---

## 5. Ürün Gereksinimleri

### 5.1 Fonksiyonel gereksinimler

#### FR-01 — Etki hesaplama motoru
**Öncelik:** P0 (zorunlu)

Teslim edilen ilan için aşağıdaki metrikleri hesapla:

| Metrik | Birim | Kaynak ilanı | Atık ilanı |
|--------|-------|--------------|------------|
| CO₂e tasarrufu | kg CO₂e | ✓ | ✓ (geri dönüşüm) |
| Su tasarrufu | litre | ✓ | — |
| Yönlendirilen atık | kg | — | ✓ |
| Yeniden kullanım | adet | ✓ | — |
| Döngüsel ekonomi skoru | puan | ✓ | ✓ |

**Hesaplama tetikleyicisi:** `ilan_durumu` → `"Teslim Edildi"` geçişi (yalnızca ilk geçişte kayıt; tekrar hesaplama yok).

**Girdiler:**
- `tur`: `kaynak` | `atik`
- `kategori`: `KATEGORILER_KAYNAK` / `KATEGORILER_ATIK`
- `ilan_id`, `user_id`
- `teslim_tarihi`

**Çıktı:** `CevreselEtki` kaydı (bkz. §6.1).

---

#### FR-02 — Kategori katsayı tablosu
**Öncelik:** P0

`constants.py` veya `data/etki_katsayilari.json` içinde yapılandırılabilir katsayılar:

**Kaynak (reuse) — örnek varsayılanlar:**

| Kategori | CO₂e (kg) | Su (L) | Tahmini ağırlık (kg) |
|----------|-----------|--------|----------------------|
| Mobilya | 45 | 800 | 25 |
| Elektronik | 35 | 400 | 3 |
| Giysi | 12 | 2500 | 0.5 |
| Kitap | 2 | 50 | 0.3 |
| Beyaz Eşya | 80 | 1200 | 60 |
| Diğer | 10 | 200 | 2 |

**Atık (recycle) — örnek varsayılanlar:**

| Kategori | Yönlendirilen kg | CO₂e önlenen (kg) |
|----------|------------------|-------------------|
| Plastik | 2 | 3 |
| Kağıt | 5 | 2 |
| Cam | 8 | 0.5 |
| Metal | 3 | 5 |
| Elektronik Atık | 4 | 15 |
| Tekstil | 2 | 4 |
| Diğer | 1 | 1 |

> **Not:** Katsayılar literatür / ÇEVKO / WRAP benzeri ortalama değerlerden türetilir; UI’da “tahmini” ibaresi zorunludur. Metodoloji sayfasında kaynak listesi yayınlanır.

---

#### FR-03 — Anasayfa çevresel özet
**Öncelik:** P0

Mevcut “Platform İstatistikleri” bölümünün altına veya yanına **“Çevresel Etkimiz”** kartları:

1. Toplam CO₂e tasarrufu (kg)
2. Toplam su tasarrufu (L)
3. Yeniden kullanılan eşya (adet — teslim edilen kaynak)
4. Yönlendirilen atık (kg — teslim edilen atık)

- Sayılar `1000+` formatında kısaltılabilir (ör. `1,2 ton CO₂e`).
- Her kartta bilgi ikonu → metodoloji sayfasına link.
- Misafir erişimine açık.

---

#### FR-04 — Kişisel etki paneli (`/etki-panelim`)
**Öncelik:** P0

Giriş zorunlu. İçerik:

- **Özet kartlar:** kullanıcının toplam CO₂e, su, teslim sayısı, döngüsel ekonomi skoru
- **Son teslimler listesi:** tarih, tür, kategori, etki özeti
- **Basit grafik:** son 6 ay aylık CO₂e (Chart.js veya CSS bar)
- **Karşılaştırma metni:** “Bu kadar CO₂e ≈ X km araba yolculuğu” (opsiyonel, sabit dönüşüm)

Profil sayfasında özet widget + “Detaylı Etki Paneli” linki.

---

#### FR-05 — Teslim anı geri bildirimi
**Öncelik:** P1

`ilan_durumu` → `Teslim Edildi` sonrası:
- Flash mesaj: *“Tebrikler! Bu paylaşımınla yaklaşık X kg CO₂e tasarrufu sağlandı.”*
- Bildirim kaydı (`Bildirim` modeli, `tur='etki'`)

---

#### FR-06 — Admin etki paneli
**Öncelik:** P1

`/admin` içinde yeni sekme veya bölüm:
- Toplam platform metrikleri
- Kategori bazlı dağılım (tablo)
- İl bazlı dağılım (User.il üzerinden)
- Son 30 gün teslim trendi
- CSV export (opsiyonel v1.1)

---

#### FR-07 — Metodoloji sayfası (`/cevresel-etki-metodolojisi`)
**Öncelik:** P0

Statik sayfa:
- Hangi verilerin kullanıldığı
- Katsayı tabloları
- “Tahmini değerdir” uyarısı
- SDG 12 bağlantısı
- Kaynakça listesi

---

#### FR-08 — API endpoint (opsiyonel v1)
**Öncelik:** P2

```
GET /api/etki/ozet          → genel toplamlar (public)
GET /api/etki/benim         → current_user özeti (auth)
GET /api/etki/ilan/<id>     → tek ilan etkisi (sahip veya admin)
```

JSON formatı; ileride belediye dashboard entegrasyonu için.

---

### 5.2 Fonksiyonel olmayan gereksinimler

| ID | Gereksinim | Hedef |
|----|------------|-------|
| NFR-01 | Performans | Anasayfa etki sorgusu < 200 ms (önbellek veya aggregate tablo) |
| NFR-02 | Doğruluk | Aynı ilan için yalnızca 1 etki kaydı (unique constraint) |
| NFR-03 | Şeffaflık | Tüm UI metriklerinde “tahmini” etiketi |
| NFR-04 | Erişilebilirlik | Renk körlüğü uyumlu grafikler; sayısal değer her zaman metinle |
| NFR-05 | Dark mode | Mevcut `app.css` tema değişkenleriyle uyumlu |
| NFR-06 | Test | Hesaplama motoru için unit test; teslim akışı entegrasyon testi |
| NFR-07 | Migrasyon | Mevcut “Teslim Edildi” ilanlar için tek seferlik backfill script |

---

## 6. Teknik Tasarım

### 6.1 Yeni veri modeli

```python
class CevreselEtki(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kaynak_id = db.Column(db.Integer, db.ForeignKey("kaynak.id"), nullable=True)
    atik_id = db.Column(db.Integer, db.ForeignKey("atik.id"), nullable=True)
    tur = db.Column(db.String(20), nullable=False)  # kaynak | atik
    kategori = db.Column(db.String(50), nullable=False)
    co2e_kg = db.Column(db.Float, nullable=False, default=0)
    su_litre = db.Column(db.Float, nullable=False, default=0)
    atik_kg = db.Column(db.Float, nullable=False, default=0)
    dongusel_skor = db.Column(db.Integer, nullable=False, default=0)
    hesaplama_versiyonu = db.Column(db.String(10), default="1.0")
    timestamp = db.Column(db.DateTime, default=tr_time)

    __table_args__ = (
        db.UniqueConstraint("kaynak_id", name="uq_etki_kaynak"),
        db.UniqueConstraint("atik_id", name="uq_etki_atik"),
    )
```

### 6.2 Servis katmanı

**Dosya:** `services/impact.py`

```python
def hesapla_etki(tur: str, kategori: str) -> dict: ...
def kaydet_etki(ilan, tur: str) -> CevreselEtki | None: ...
def platform_ozeti() -> dict: ...
def kullanici_ozeti(user_id: int) -> dict: ...
def backfill_mevcut_teslimler() -> int: ...
```

### 6.3 Entegrasyon noktaları

| Dosya | Değişiklik |
|-------|------------|
| `blueprints/ilan.py` | `ilan_durum_guncelle` → `kaydet_etki()` çağrısı |
| `blueprints/main.py` | `anasayfa()` → `platform_ozeti()` |
| `blueprints/auth.py` veya yeni `impact_bp` | `/etki-panelim`, metodoloji |
| `blueprints/admin.py` | Admin etki bölümü |
| `blueprints/api.py` | `/api/etki/*` |
| `utils.py` | `ensure_schema()` → `cevresel_etki` tablosu |
| `templates/home.html` | Çevresel kartlar |
| `templates/profil.html` | Özet widget |
| `templates/etki_panelim.html` | Yeni şablon |
| `templates/etki_metodoloji.html` | Yeni şablon |
| `constants.py` | `ETKI_KATSAYILARI` |
| `migration.py` veya `scripts/backfill_etki.py` | Backfill |

### 6.4 Döngüsel ekonomi skoru formülü (v1)

```
dongusel_skor = round(co2e_kg * 10) + (50 if tur == "kaynak" else 30)
```

Basit, anlaşılır; v2’de yeşil puan sistemiyle birleştirilebilir.

### 6.5 Önbellek stratejisi (opsiyonel)

`platform_ozeti` her anasayfa yüklemesinde aggregate sorgu yapabilir. Teslim sayısı < 10.000 iken doğrudan SQL `SUM` yeterli. Ölçek büyürse:
- `PlatformEtkiOzet` aggregate tablosu (teslimde güncelle), veya
- Flask-Caching 5 dk TTL

---

## 7. Kullanıcı Deneyimi

### 7.1 Kullanıcı akışları

#### Akış A — Teslim → Etki görme
```
İlanlarım → Durum: Teslim Edildi seç
  → Backend: etki hesapla + kaydet + guven_puani++
  → Flash: "≈ X kg CO₂e tasarrufu"
  → Bildirim oluştur
  → Kullanıcı profil / etki panelinde görür
```

#### Akış B — Misafir — Platform değeri
```
Anasayfa → Çevresel Etkimiz kartları
  → (i) Metodoloji sayfası
```

#### Akış C — Admin raporlama
```
Admin → Çevresel Etki sekmesi
  → Kategori / il kırılımı
  → (opsiyonel) CSV indir
```

### 7.2 UI bileşenleri

Mevcut tasarım sistemi (`app.css`) kullanılacak:
- `stat-card` — metrik kartları
- `page-header` — panel başlığı
- `hero-section` altı vurgu bandı (opsiyonel)
- Renk kodu: yeşil/teal (`--brand-accent`)

**Örnek anasayfa kartı:**
```
┌─────────────────────────┐
│  🌱 1.240 kg            │
│  CO₂e tasarrufu*        │
│  [i] tahmini değer      │
└─────────────────────────┘
```

### 7.3 Metin / dil kuralları
- Her metrik yanında `*` veya `(tahmini)`
- “Kurtarılan”, “önlenen”, “tasarruf” fiilleri tutarlı kullanılır
- Bilimsel iddia yapılmaz; “yaklaşık”, “tahmini” zorunlu

---

## 8. Kabul Kriterleri (Acceptance Criteria)

### AC-01 — Hesaplama
- [ ] Mobilya kategorili teslim edilmiş kaynak için `co2e_kg >= 45` (katsayı tablosuna göre)
- [ ] Aynı ilan ikinci kez “Teslim Edildi” yapılırsa yeni `CevreselEtki` kaydı oluşmaz
- [ ] Aktif/Rezerve ilanlar etki toplamına dahil edilmez

### AC-02 — Anasayfa
- [ ] Misafir kullanıcı 4 çevresel metrik görür
- [ ] Teslim sayısı 0 ise metrikler 0 gösterilir (hata vermez)
- [ ] Metodoloji linki çalışır

### AC-03 — Kişisel panel
- [ ] Giriş yapmamış kullanıcı `/etki-panelim` → login redirect
- [ ] Kullanıcı yalnızca kendi teslimlerinin etkisini görür
- [ ] Son 5 teslim listelenir

### AC-04 — Admin
- [ ] Admin olmayan `/admin` etki bölümüne erişemez
- [ ] Kategori kırılımı toplamı genel toplamla tutarlı

### AC-05 — Test & migrasyon
- [ ] `pytest` — en az 5 yeni unit test geçer
- [ ] Backfill script mevcut teslim ilanları işler
- [ ] Dark mode’da kartlar okunabilir

---

## 9. Uygulama Fazları

### Faz 1 — MVP (1–2 hafta)
| Görev | Öncelik |
|-------|---------|
| `CevreselEtki` model + migration | P0 |
| `services/impact.py` + katsayılar | P0 |
| `ilan_durum_guncelle` entegrasyonu | P0 |
| Anasayfa kartları | P0 |
| Metodoloji sayfası | P0 |
| Unit testler | P0 |
| Backfill script | P0 |

### Faz 2 — Kişisel & Admin (1 hafta)
| Görev | Öncelik |
|-------|---------|
| `/etki-panelim` sayfası | P1 |
| Profil widget | P1 |
| Teslim flash + bildirim | P1 |
| Admin etki sekmesi | P1 |

### Faz 3 — Gelişmiş (v1.1+)
| Görev | Öncelik |
|-------|---------|
| API endpoint’leri | P2 |
| Chart.js grafikler | P2 |
| CSV export | P2 |
| Karşılaştırma metinleri (km araba vb.) | P2 |
| Yeşil puan ile birleştirme | P2 |

---

## 10. Riskler ve Azaltma

| Risk | Olasılık | Etki | Azaltma |
|------|----------|------|---------|
| Katsayıların bilimsel eleştirisi | Orta | Yüksek | “Tahmini” etiket + metodoloji + kaynakça |
| Sahte “Teslim Edildi” ile şişirme | Orta | Orta | İleride alıcı onayı (v2); şimdilik güven puanı + şikayet |
| Performans (aggregate sorgular) | Düşük | Orta | Index + önbellek |
| Mevcut DB migrasyon hatası | Düşük | Yüksek | `ensure_schema` + test DB’de doğrula |

---

## 11. Metrikler (Ürün başarısı)

| KPI | Başlangıç | 3 ay hedef |
|-----|----------|------------|
| Teslim oranı (ilan başına) | baseline | +20% |
| Etki paneli görüntüleme | 0 | MAU’nun %30’u |
| Ortalama kullanıcı CO₂e tasarrufu | — | ölçülür |
| Teknofest raporu hazırlık | — | metodoloji + demo veri seti |

---

## 12. Teknofest / Yarışma Uyumu

Bu modül doğrudan şu kriterleri destekler:

- **Özgünlük:** İlan platformu + ölçülebilir çevresel etki birleşimi
- **Toplumsal fayda:** Somut CO₂e / su / atık metrikleri
- **Sürdürülebilirlik:** SDG 12 — Sorumlu Tüketim ve Üretim
- **Uygulanabilirlik:** Mevcut `Teslim Edildi` akışına minimal ekleme
- **Demo etkisi:** Anasayfa ve canlı teslim senaryosu jüri için güçlü

**Sunum cümlesi:**  
*“AtıkPort, her teslim edilen paylaşımı kategori bazlı çevresel etkiye dönüştürerek döngüsel ekonomiyi sayısallaştıran ilk Türkçe AI destekli platformdur.”*

---

## 13. Açık Sorular

| # | Soru | Önerilen karar | Karar veren |
|---|------|----------------|-------------|
| 1 | Katsayıları JSON mu Python dict mi? | `data/etki_katsayilari.json` — kolay güncelleme | Geliştirici |
| 2 | Alıcı onayı gerekli mi? | v1 hayır; v2 değerlendir | Ürün |
| 3 | Grafik kütüphanesi? | Chart.js CDN (zaten Bootstrap var) | Geliştirici |
| 4 | Eski teslimler backfill? | Evet, tek seferlik script | Geliştirici |

---

## 14. Ekler

### Ek A — Dosya listesi (tahmini)

```
models.py                          # CevreselEtki
constants.py                       # veya data/etki_katsayilari.json
services/impact.py                 # yeni
blueprints/impact.py               # yeni (opsiyonel)
scripts/backfill_etki.py           # yeni
templates/etki_panelim.html        # yeni
templates/etki_metodoloji.html     # yeni
templates/_etki_kartlari.html      # partial
tests/test_impact.py               # yeni
docs/PRD-cevresel-etki-paneli.md   # bu dosya
```

### Ek B — Örnek API yanıtı

```json
{
  "co2e_kg_toplam": 1240.5,
  "su_litre_toplam": 18500,
  "yeniden_kullanim_adet": 42,
  "atik_yonlendirme_kg": 156.0,
  "teslim_sayisi": 58,
  "hesaplama_versiyonu": "1.0",
  "tahmini": true
}
```

---

**Sonraki adım:** Faz 1 MVP geliştirmesine başlamak için bu PRD onaylandıktan sonra `services/impact.py` ve model implementasyonu yapılacaktır.
