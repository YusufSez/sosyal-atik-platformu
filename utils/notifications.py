from urllib.parse import urlparse

from flask import has_request_context, request


def safe_redirect_url(target, default_endpoint="main.anasayfa"):
    """Harici open-redirect riskini önler; yalnızca aynı host veya göreli yollar."""
    if not target:
        from flask import url_for
        return url_for(default_endpoint)
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        host = (request.host or "").split(":")[0].lower()
        ref_host = (parsed.netloc or "").split(":")[0].lower()
        if not ref_host or ref_host != host:
            from flask import url_for
            return url_for(default_endpoint)
    return target


def safe_notification_link(link, *, site_url=None):
    """Bildirim href: göreli yol veya aynı origin; javascript:/data: reddedilir."""
    if not link:
        return None
    link = str(link).strip()
    if not link:
        return None
    if link.startswith("//"):
        return None
    lower = link.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return None
    parsed = urlparse(link)
    if not parsed.scheme and not parsed.netloc:
        return link if link.startswith("/") else f"/{link}"
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https"):
        ref_host = (parsed.netloc or "").split(":")[0].lower()
        if site_url:
            site_host = urlparse(site_url).netloc.split(":")[0].lower()
            if ref_host and ref_host == site_host:
                return link
        if has_request_context():
            req_host = (request.host or "").split(":")[0].lower()
            if ref_host and ref_host == req_host:
                return link
        return None
    return None
