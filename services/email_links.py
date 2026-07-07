"""E-posta ve dış bağlantılar için mutlak URL oluşturma."""

from urllib.parse import urlparse

from flask import current_app, url_for


def absolute_url_for(endpoint: str, **values) -> str:
    """
    Mutlak uygulama URL'si üretir.

    SITE_URL tanımlıysa (ör. http://localhost:8080, https://alanadim.com)
    şema ve host bu değerden alınır. Tanımlı değilse url_for(..., _external=True).
    """
    site_url = (current_app.config.get("SITE_URL") or "").strip().rstrip("/")
    if not site_url:
        return url_for(endpoint, _external=True, **values)

    parsed = urlparse(site_url)
    scheme = parsed.scheme or "https"
    base_url = f"{scheme}://{parsed.netloc}/"
    old_server = current_app.config.get("SERVER_NAME")
    old_scheme = current_app.config.get("PREFERRED_URL_SCHEME")
    try:
        if parsed.netloc:
            current_app.config["SERVER_NAME"] = parsed.netloc
        current_app.config["PREFERRED_URL_SCHEME"] = scheme
        with current_app.test_request_context(base_url=base_url):
            return url_for(endpoint, _external=True, **values)
    finally:
        if old_server is not None:
            current_app.config["SERVER_NAME"] = old_server
        if old_scheme is not None:
            current_app.config["PREFERRED_URL_SCHEME"] = old_scheme
