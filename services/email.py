"""E-posta bildirimleri için stub servis. SMTP yapılandırılmadığında log'a yazar."""

import logging

logger = logging.getLogger(__name__)


def eposta_gonder(alici, konu, icerik):
    """SMTP entegrasyonu eklendiğinde bu fonksiyon genişletilebilir."""
    logger.info("E-posta (stub): alici=%s konu=%s icerik=%s", alici, konu, icerik[:80])
