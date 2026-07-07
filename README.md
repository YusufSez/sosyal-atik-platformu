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
flask db upgrade             # şemayı oluştur / güncelle
python migration.py          # isteğe bağlı: örnek veri ve backfill
python app.py
```

Uygulama varsayılan olarak `http://127.0.0.1:5000` adresinde çalışır.

## Veritabanı migration'ları (Flask-Migrate / Alembic)

Şema değişiklikleri `db.create_all()` yerine Alembic revision'ları ile yönetilir. SQLite ve PostgreSQL aynı migration dosyalarını kullanır.

```bash
# Ortam (Windows PowerShell)
$env:FLASK_APP = "app.py"

# İlk kurulum veya deploy sonrası
flask db upgrade

# Model değişikliğinden sonra yeni revision
flask db migrate -m "açıklayıcı mesaj"
flask db upgrade

# Mevcut revision
flask db current

# Bir adım geri (dikkatli kullanın)
flask db downgrade
```

**Üretim / PostgreSQL:** `AUTO_CREATE_DB=False` (varsayılan). Uygulama başlamadan önce `flask db upgrade` çalıştırın.

**Yerel SQLite (DEBUG=True):** `AUTO_CREATE_DB` tanımsızsa `create_all()` otomatik çalışır; yine de `flask db upgrade` önerilir.

**SQLite → PostgreSQL veri aktarımı:** Önce hedef veritabanında `flask db upgrade`, ardından:

```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite-path site.db
```

`scripts/migrate_sqlite_to_postgres.py` şemayı Alembic ile oluşturur; veri kopyalama mevcut tablolara yapılır.

**Mevcut veritabanı zaten güncel şemadaysa** (`create_all` ile oluşturulmuş SQLite veya PostgreSQL), tabloları yeniden oluşturmadan Alembic kaydını işaretleyin:

```bash
flask db stamp head
```

## Admin Kullanıcısı

Veritabanında bir kullanıcının `is_admin` alanını `1` yapın:

```sql
UPDATE user SET is_admin = 1 WHERE email = 'sizin@email.com';
```

Ardından `/admin` sayfasına erişebilirsiniz.

## Docker

### Yerel geliştirme (SQLite)

```bash
docker compose up --build
```

### Üretim stack — PostgreSQL + Nginx

Önkoşul: proje kökünde `.env` dosyasında en az şunlar tanımlı olmalı:

```env
SECRET_KEY=...
POSTGRES_PASSWORD=guclu-sifre
SITE_URL=http://localhost:8080
USE_POSTGRES=True
POSTGRES_DB=atikport
POSTGRES_USER=postgres
```

`deploy/docker-compose.prod.yml` web servisinde `POSTGRES_HOST=postgres` olarak ayarlar; yerel `.env` içindeki `POSTGRES_HOST=localhost` Docker içinde geçersiz kılınır.

```bash
cd deploy
docker compose -f docker-compose.prod.yml up --build -d
```

| Servis    | Açıklama                          |
|-----------|-----------------------------------|
| `postgres`| PostgreSQL 17, kalıcı `pgdata` volume |
| `web`     | Gunicorn, `flask db upgrade` otomatik |
| `nginx`   | http://localhost:8080             |

Durum kontrolü:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs postgres --tail 20
docker compose -f docker-compose.prod.yml logs web --tail 30
curl http://localhost:8080/health
```

### SQLite → PostgreSQL veri aktarımı (Docker)

Mevcut `site.db` dosyasını container içindeki PostgreSQL'e aktarmak için:

```bash
cd deploy
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml --profile migrate run --rm migrate-sqlite
```

Üzerine yazmak için:

```bash
docker compose -f docker-compose.prod.yml --profile migrate run --rm \
  --entrypoint /bin/sh migrate-sqlite -c \
  "python scripts/wait_for_postgres.py && python scripts/migrate_sqlite_to_postgres.py --sqlite-path /import/site.db --reset"
```

Yerel (Docker dışı) aktarım:

```bash
# .env: USE_POSTGRES=True, POSTGRES_HOST=localhost, POSTGRES_PASSWORD=...
flask db upgrade
python scripts/migrate_sqlite_to_postgres.py --sqlite-path site.db
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
migrations/         # Alembic revision'ları (Flask-Migrate)
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
| `FLASK_APP` | Flask CLI giriş noktası (`app.py`) |
| `AUTO_CREATE_DB` | `True` ise DEBUG+SQLite'ta `create_all()`; üretimde `False` |
| `USE_POSTGRES` | PostgreSQL kullan (`True`/`False`); Docker prod compose varsayılan `true` |
| `POSTGRES_HOST` | PostgreSQL sunucusu (`localhost` yerel, `postgres` Docker ağı) |
| `POSTGRES_PASSWORD` | PostgreSQL şifresi (Docker postgres servisi için zorunlu) |
| `DATABASE_URL` | Tam DB bağlantı dizesi (öncelikli) |
| `ALLOW_SEED_ROUTE` | `/seed` endpoint'ini açar |
| `RATELIMIT_STORAGE_URI` | Rate limit depolama (örn. `redis://localhost:6379`) |
| `SITE_URL` | Kamuya açık site adresi; e-posta doğrulama ve şifre sıfırlama linkleri (ör. `http://localhost:8080`, `https://alanadim.com`) |

## Notlar

- `scripts/test_ai.py` — Gemini AI fonksiyonlarını manuel test etmek için
- Production'da `RATELIMIT_STORAGE_URI=redis://...` kullanın
- Docker Linux ortamı içindir; Windows'ta native `gunicorn` çalışmaz
- E-posta bildirimleri stub olarak loglanır; SMTP entegrasyonu `services/email.py` üzerinden genişletilebilir
