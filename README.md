# AtıkPort — AI Destekli Atık & Kaynak Paylaşım Platformu

Flask tabanlı web uygulaması. Kullanıcılar kaynak (yeniden kullanılabilir eşya) ve atık ilanları paylaşır; Google Gemini görselleri analiz ederek kategori tahmini ve moderasyon yapar.

## Özellikler

- Kaynak ve atık ilan yönetimi (CRUD, durum: Aktif / Rezerve / Teslim Edildi)
- Gemini AI ile görsel kategori + moderasyon
- Kullanıcı kayıt/giriş (pbkdf2 şifreleme, eski sha256_crypt uyumlu)
- Mesajlaşma ve bildirimler
- Favoriler, yorumlar, görüntülenme sayacı
- Harita ile atık merkezleri (İBB açık veri)
- CSRF koruması ve rate limiting
- Admin paneli

## Kurulum

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env       # GEMINI_API_KEY ve SECRET_KEY girin
python migration.py
python app.py
```

Uygulama varsayılan olarak `http://127.0.0.1:5000` adresinde çalışır.

## Admin Kullanıcısı

Veritabanında bir kullanıcının `is_admin` alanını `1` yapın:

```sql
UPDATE user SET is_admin = 1 WHERE email = 'sizin@email.com';
```

Ardından `/admin` sayfasına erişebilirsiniz.

## Docker

```bash
docker compose up --build
```

## Test

```bash
pytest tests/ -v
```

## Proje Yapısı

```
app.py              # Giriş noktası
factory.py          # Flask uygulama fabrikası
models.py           # SQLAlchemy modelleri
constants.py        # Kategori ve sabitler
utils.py            # Yardımcı fonksiyonlar
helpers.py          # Gemini AI entegrasyonu
blueprints/         # Route modülleri
templates/          # Jinja2 şablonları
static/             # Statik dosyalar
```

## Ortam Değişkenleri

| Değişken | Açıklama |
|----------|----------|
| `SECRET_KEY` | Flask oturum güvenliği |
| `GEMINI_API_KEY` | Google Gemini API anahtarı |
| `DEBUG` | Geliştirme modu (`True`/`False`) |
| `ALLOW_SEED_ROUTE` | `/seed` endpoint'ini açar |
| `RATELIMIT_STORAGE_URI` | Rate limit depolama (örn. `redis://localhost:6379`) |

## Notlar

- `scripts/test_ai.py` — Gemini AI fonksiyonlarını manuel test etmek için
- Production'da `RATELIMIT_STORAGE_URI=redis://...` kullanın
- Docker Linux ortamı içindir; Windows'ta native `gunicorn` çalışmaz
- E-posta bildirimleri stub olarak loglanır; SMTP entegrasyonu `services/email.py` üzerinden genişletilebilir
