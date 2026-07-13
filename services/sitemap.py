"""Public XML sitemap ve robots.txt üretimi."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from flask import current_app, url_for

from constants import KATEGORILER_ATIK, KATEGORILER_KAYNAK
from content.kurumsal import KURUMSAL_SAYFALAR
from models import Atik, Kaynak
from services.ilan_moderation import public_ilan_base_filter

# Statik içerik lastmod — kurumsal içerik dosyasının mtime'si
_STATIC_LASTMOD = date.fromtimestamp(
    Path(__file__).resolve().parents[1].joinpath("content", "kurumsal.py").stat().st_mtime
)

_ROBOTS_DISALLOW = (
    "/admin/",
    "/belediye/",
    "/bakanlik/",
    "/minister/",
    "/kurum/",
    "/profil/",
    "/profil",
    "/mesajlar/",
    "/mesajlarim",
    "/ayarlar/",
    "/api/",
    "/marketplace/",
    "/socket-test",
    "/health",
)


@dataclass(frozen=True)
class SitemapUrl:
    loc: str
    lastmod: date | None = None
    changefreq: str | None = None
    priority: float | None = None


def site_base_url() -> str:
    """SITE_URL; yoksa request kökü (test / lokal). Hardcode domain yok."""
    from flask import has_request_context, request

    configured = (current_app.config.get("SITE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    if has_request_context():
        return request.url_root.rstrip("/")
    return ""


def _abs(path: str) -> str:
    base = site_base_url()
    if not path.startswith("/"):
        path = "/" + path
    if not base:
        return path
    return f"{base}{path}"


def _fmt_day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _entry(
    path: str,
    *,
    lastmod: date | None = None,
    changefreq: str = "monthly",
    priority: float = 0.5,
) -> SitemapUrl:
    return SitemapUrl(
        loc=_abs(path),
        lastmod=lastmod or _STATIC_LASTMOD,
        changefreq=changefreq,
        priority=priority,
    )


def collect_sitemap_urls() -> list[SitemapUrl]:
    """Yalnızca public, indexlenebilir URL'ler (login/admin/api yok)."""
    seen: set[str] = set()
    urls: list[SitemapUrl] = []

    def add(entry: SitemapUrl) -> None:
        if entry.loc in seen:
            return
        seen.add(entry.loc)
        urls.append(entry)

    # Ana ve auth (public)
    add(_entry("/", changefreq="daily", priority=1.0))
    add(_entry(url_for("auth.giris"), changefreq="monthly", priority=0.6))
    add(_entry(url_for("auth.kayit"), changefreq="monthly", priority=0.6))

    # Paneller (public liste)
    add(_entry(url_for("kaynak.kaynak_panel"), changefreq="hourly", priority=0.9))
    add(_entry(url_for("atik.atik_panel"), changefreq="hourly", priority=0.9))
    add(_entry(url_for("gamification.liderlik"), changefreq="daily", priority=0.5))
    add(_entry(url_for("impact.metodoloji"), changefreq="yearly", priority=0.4))
    add(_entry(url_for("support.destek"), changefreq="monthly", priority=0.5))

    # Kurumsal
    add(_entry(url_for("main.iletisim"), changefreq="monthly", priority=0.7))
    add(_entry(url_for("main.site_haritasi"), changefreq="monthly", priority=0.3))
    for slug in KURUMSAL_SAYFALAR:
        add(
            _entry(
                url_for("main.kurumsal_sayfa", slug=slug),
                changefreq="monthly",
                priority=0.6,
            )
        )

    # Kategori filtre sayfaları
    for kat in KATEGORILER_KAYNAK:
        path = f"{url_for('kaynak.kaynak_panel')}?kategori={quote(kat)}"
        add(_entry(path, changefreq="daily", priority=0.55))
    for kat in KATEGORILER_ATIK:
        path = f"{url_for('atik.atik_panel')}?kategori={quote(kat)}"
        add(_entry(path, changefreq="daily", priority=0.55))

    # Yayındaki public ilanlar (Kaynak / Atık)
    for row in (
        public_ilan_base_filter(Kaynak.query, Kaynak)
        .order_by(Kaynak.id.desc())
        .limit(10_000)
        .all()
    ):
        add(
            _entry(
                url_for("kaynak.kaynak_detay", id=row.id),
                lastmod=_fmt_day(getattr(row, "tarih", None)),
                changefreq="weekly",
                priority=0.7,
            )
        )
    for row in (
        public_ilan_base_filter(Atik.query, Atik)
        .order_by(Atik.id.desc())
        .limit(10_000)
        .all()
    ):
        add(
            _entry(
                url_for("atik.atik_detay", id=row.id),
                lastmod=_fmt_day(getattr(row, "tarih", None)),
                changefreq="weekly",
                priority=0.7,
            )
        )

    # Marketplace tamamen login_required — sitemap'e eklenmez
    return urls


def render_sitemap_xml(entries: list[SitemapUrl] | None = None) -> str:
    if entries is None:
        entries = collect_sitemap_urls()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for item in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(item.loc)}</loc>")
        if item.lastmod is not None:
            lines.append(f"    <lastmod>{item.lastmod.isoformat()}</lastmod>")
        if item.changefreq:
            lines.append(f"    <changefreq>{escape(item.changefreq)}</changefreq>")
        if item.priority is not None:
            lines.append(f"    <priority>{item.priority:.1f}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_robots_txt() -> str:
    sitemap_loc = _abs("/sitemap.xml")
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
    ]
    for path in _ROBOTS_DISALLOW:
        lines.append(f"Disallow: {path}")
    lines.extend(["", f"Sitemap: {sitemap_loc}", ""])
    return "\n".join(lines)


def default_seo_description() -> str:
    name = current_app.config.get("SITE_NAME") or "AtıkPort"
    return (
        f"{name} — atık ve kaynak paylaşım platformu. "
        "Sürdürülebilir alışveriş, bağış ve geri dönüşüm ilanları."
    )


def build_canonical_url() -> str:
    from flask import request

    base = site_base_url()
    path = request.path or "/"
    # Query: yalnızca güvenli filtreler (kategori) canonical'a alınır
    kategori = (request.args.get("kategori") or "").strip()
    if kategori:
        path = f"{path}?kategori={quote(kategori)}"
    if base:
        return f"{base}{path}"
    return request.url.split("#", 1)[0]
