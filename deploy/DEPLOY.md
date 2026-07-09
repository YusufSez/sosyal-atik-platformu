# atikport.com VPS Deployment Guide

Bu rehber, AtıkPort'u `atikport.com` domain'i ile VPS'e yayınlamak için adım adım talimatlar içerir.

## Önkoşullar

- Ubuntu 22.04/24.04 VPS (min. 2 GB RAM önerilir)
- `atikport.com` domain erişimi
- GitHub repo erişimi
- Brevo, Gemini, Cloudflare Turnstile API anahtarları

---

## 1. VPS Hazırlığı

SSH ile sunucuya bağlanın ve bootstrap script'ini çalıştırın:

```bash
curl -fsSL https://raw.githubusercontent.com/YusufSez/sosyal-atik-platformu/main/deploy/scripts/vps-bootstrap.sh | sudo bash
```

Veya depo klonlandıktan sonra:

```bash
sudo bash deploy/scripts/vps-bootstrap.sh
```

---

## 2. DNS Ayarları

VPS IP adresinizi öğrenin: `curl -4 ifconfig.me`

### Cloudflare (önerilen)

| Kayıt | Tip | Değer |
|-------|-----|-------|
| `atikport.com` | A | `VPS_IP` |
| `www` | CNAME | `atikport.com` |

Cloudflare nameserver'larını domain satıcı paneline girin. SSL/TLS modu: **Full (strict)**.

### Domain satıcı paneli

| Kayıt | Tip | Değer |
|-------|-----|-------|
| `@` | A | `VPS_IP` |
| `www` | CNAME | `atikport.com` |

Doğrulama:

```bash
dig atikport.com +short
# VPS IP dönmeli
```

---

## 3. Depoyu Klonlayın ve .env Oluşturun

```bash
sudo mkdir -p /opt/atikport
sudo chown $USER:$USER /opt/atikport
cd /opt
git clone https://github.com/YusufSez/sosyal-atik-platformu.git atikport
cd atikport
cp deploy/env.production.example .env
nano .env   # Tüm <...> değerlerini doldurun
```

**Kritik değerler:**

- `SECRET_KEY` — `python -c "import secrets; print(secrets.token_hex(32))"`
- `POSTGRES_PASSWORD` — güçlü şifre
- `SITE_URL=https://atikport.com`
- `FORCE_HTTPS=True`
- `TURNSTILE_*` — hostname: `atikport.com`
- `BREVO_API_KEY` — VPS için önerilir
- `SOCKETIO_CORS_ORIGINS=https://atikport.com,https://www.atikport.com`

### Bind mount izinleri (upload / log)

`docker-compose.prod.yml` host dizinlerini bağlar: `static/item_pics`, `static/profile_pics`, `logs`.

Container entrypoint bu dizinlerin sahipliğini `atikport` (UID **1000**) kullanıcısına ayarlamaya çalışır. Host'ta dizinler root veya farklı bir kullanıcıya aitse ve `chown` başarısız olursa yükleme/log yazımı `PermissionError` verebilir:

```bash
sudo chown -R 1000:1000 static/item_pics static/profile_pics logs
```

Windows bind mount kullanıyorsanız Docker Desktop genelde yazmayı izin verir; sorun yaşarsanız named volume veya WSL2 dosya yolu tercih edin.

---

## 4. Veri Taşıma (Yerel → VPS)

### 4a. Yerel makinede dump

```bash
cd deploy
bash scripts/pg-dump-local.sh ../atikport.dump
```

### 4b. VPS'e kopyala

```bash
scp atikport.dump deploy@VPS_IP:/opt/atikport/
VPS_HOST=deploy@VPS_IP bash scripts/upload-sync.sh
```

### 4c. VPS'te restore

```bash
cd /opt/atikport/deploy
bash scripts/pg-restore.sh /opt/atikport/atikport.dump
```

---

## 5. İlk Başlatma (HTTP — SSL öncesi)

DNS yayıldıktan sonra:

```bash
cd /opt/atikport/deploy
docker compose -f docker-compose.prod.yml -f docker-compose.vps-init.yml up --build -d
curl http://atikport.com/health
```

---

## 6. SSL (Let's Encrypt)

```bash
cd /opt/atikport/deploy
chmod +x scripts/*.sh
CERTBOT_EMAIL=admin@atikport.com bash scripts/ssl-init.sh
```

Bu script:

1. HTTP stack üzerinden certbot ile sertifika alır
2. HTTPS nginx'e geçer (`docker-compose.vps.yml`)
3. Certbot yenileme servisini başlatır

Doğrulama:

```bash
curl -I https://atikport.com/health
bash scripts/smoke-test.sh https://atikport.com
```

---

## 7. Harici Servisler

| Servis | Ayar |
|--------|------|
| Cloudflare Turnstile | Hostname: `atikport.com`, `www.atikport.com` |
| Brevo | Gönderici: `noreply@atikport.com`, REST API key |
| Gemini | Mevcut API key |

---

## 8. Yedekleme

```bash
sudo cp /opt/atikport/deploy/cron/atikport-backup /etc/cron.d/
sudo chmod 644 /etc/cron.d/atikport-backup
```

Manuel yedek:

```bash
bash /opt/atikport/deploy/scripts/backup-db.sh
```

---

## 9. Güncelleme

```bash
cd /opt/atikport
git pull
cd deploy
docker compose -f docker-compose.prod.yml -f docker-compose.vps.yml --profile ssl up --build -d
```

---

## Compose Dosyaları

| Dosya | Kullanım |
|-------|----------|
| `docker-compose.prod.yml` | Temel stack (yerel: `:8080`) |
| `docker-compose.vps-init.yml` | VPS HTTP (SSL öncesi, port 80) |
| `docker-compose.vps.yml` | VPS HTTPS (port 80+443) |

**Yerel test:**

```bash
docker compose -f docker-compose.prod.yml up --build -d
# http://localhost:8080
```

**VPS production:**

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.vps.yml --profile ssl up -d
# https://atikport.com
```

---

## Sorun Giderme

| Sorun | Çözüm |
|-------|-------|
| Site açılmıyor | `dig atikport.com`, UFW 80/443, `docker compose ps` |
| SSL hatası | DNS yayıldı mı? `scripts/ssl-init.sh` tekrar |
| Giriş yapılamıyor | `pg_restore` yapıldı mı? `SELECT COUNT(*) FROM "user"` |
| E-posta linkleri yanlış | `.env` → `SITE_URL=https://atikport.com` |
| Turnstile hatası | Cloudflare'de hostname ekli mi? |
