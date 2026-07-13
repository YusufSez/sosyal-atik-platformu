"""Demo Modu yönetimi — admin ayarı > .env; veri kaynağı kararı.

Karar sırası:
1) Demo Modu AÇIK → her zaman Demo Provider
2) Demo Modu KAPALI + gerçek veri yeterli → gerçek veri
3) Demo Modu KAPALI + özellik açık + veri yetersiz → Demo Provider
"""

from __future__ import annotations

from typing import Any

from flask import current_app
from flask_login import current_user

from extensions import db
from models import SystemSetting
from utils import env_to_bool, utc_now

DEMO_MODE_KEY = "demo_mode"
DEMO_AI_KEY = "demo_ai"
DEMO_DASHBOARD_KEY = "demo_dashboard"
DEMO_PREDICTION_KEY = "demo_prediction"
DEMO_SUSTAINABILITY_KEY = "demo_sustainability"
DEMO_MARKETPLACE_KEY = "demo_marketplace"

DEMO_SETTING_KEYS = (
    DEMO_MODE_KEY,
    DEMO_AI_KEY,
    DEMO_DASHBOARD_KEY,
    DEMO_PREDICTION_KEY,
    DEMO_SUSTAINABILITY_KEY,
    DEMO_MARKETPLACE_KEY,
)

_AUDIT_LABELS = {
    DEMO_MODE_KEY: ("Demo Mode Enabled", "Demo Mode Disabled"),
    DEMO_AI_KEY: ("Demo AI Enabled", "Demo AI Disabled"),
    DEMO_DASHBOARD_KEY: ("Demo Dashboard Enabled", "Demo Dashboard Disabled"),
    DEMO_PREDICTION_KEY: ("Demo Prediction Enabled", "Demo Prediction Disabled"),
    DEMO_SUSTAINABILITY_KEY: ("Demo Sustainability Enabled", "Demo Sustainability Disabled"),
    DEMO_MARKETPLACE_KEY: ("Demo Marketplace Enabled", "Demo Marketplace Disabled"),
}

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "açık", "acik"})


def _parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in _TRUE_VALUES


def _db_value(key: str) -> str | None:
    """DB'de kayıt yoksa None; varsa ham value."""
    try:
        row = SystemSetting.query.filter_by(key=key).first()
    except Exception:
        # Tablo henüz yoksa (migration öncesi) sessizce env'e düş.
        return None
    if row is None:
        return None
    return row.value


def _env_demo_mode() -> bool:
    try:
        cfg = current_app.config.get("DEMO_MODE")
        if cfg is not None:
            return bool(cfg)
    except RuntimeError:
        pass
    import os

    return env_to_bool(os.getenv("DEMO_MODE"), default=False)


def get_setting_bool(key: str, *, default: bool = False) -> bool:
    raw = _db_value(key)
    if raw is not None:
        return _parse_bool(raw)
    return default


def is_demo_mode() -> bool:
    """Admin ayarı varsa onu kullan; yoksa .env DEMO_MODE."""
    raw = _db_value(DEMO_MODE_KEY)
    if raw is not None:
        return _parse_bool(raw)
    return _env_demo_mode()


def use_demo_ai() -> bool:
    return is_demo_mode() or get_setting_bool(DEMO_AI_KEY, default=False)


def use_demo_dashboard() -> bool:
    return is_demo_mode() or get_setting_bool(DEMO_DASHBOARD_KEY, default=False)


def use_demo_prediction() -> bool:
    return is_demo_mode() or get_setting_bool(DEMO_PREDICTION_KEY, default=False)


def use_demo_sustainability() -> bool:
    return is_demo_mode() or get_setting_bool(DEMO_SUSTAINABILITY_KEY, default=False)


def use_demo_marketplace() -> bool:
    return is_demo_mode() or get_setting_bool(DEMO_MARKETPLACE_KEY, default=False)


def _feature_allowed(feature: str) -> bool:
    if feature == "ai":
        return use_demo_ai()
    if feature == "dashboard":
        return use_demo_dashboard()
    if feature == "prediction":
        return use_demo_prediction()
    if feature == "sustainability":
        return use_demo_sustainability()
    if feature == "marketplace":
        return use_demo_marketplace()
    return False


def should_use_demo(feature: str, *, real_data_sufficient: bool) -> bool:
    """
    1) Demo Modu açık → her zaman True
    2) Özellik kapalı → False (gerçek veri)
    3) Özellik açık + veri yetersiz → True
    4) Özellik açık + veri yeterli → False
    """
    if is_demo_mode():
        return True
    if not _feature_allowed(feature):
        return False
    return not real_data_sufficient


def is_dashboard_data_sufficient(data: dict | None) -> bool:
    if not data:
        return False
    return (data.get("toplam_aktif_ilan") or 0) > 0 or (data.get("etki_adet") or 0) > 0


def is_prediction_data_sufficient(payload: dict | None) -> bool:
    if not payload:
        return False
    history = payload.get("history") or []
    if not history:
        return False
    total = 0.0
    for row in history:
        total += float(row.get("atik_kg") or 0) + float(row.get("co2_kg") or 0)
        total += float(row.get("kaynak_adet") or 0)
    return total > 0


def is_sustainability_data_sufficient(scored: dict | None) -> bool:
    if not scored:
        return False
    metrics = scored.get("metrics") or {}
    return (metrics.get("total") or 0) > 0 or (metrics.get("etki_adet") or 0) > 0


def is_marketplace_data_sufficient(matches: list | None) -> bool:
    return bool(matches)


def is_marketplace_catalog_sufficient(listings: list | None = None) -> bool:
    """Gerçek ilan varsa demo katalog kullanılmaz (Demo Modu kapalıyken)."""
    if listings is not None:
        return len(listings) > 0
    try:
        from models import MarketplaceListing

        return MarketplaceListing.query.count() > 0
    except Exception:
        return False


def get_demo_settings() -> dict[str, bool]:
    """Admin formu ve testler için mevcut efektif ayarlar."""
    return {
        DEMO_MODE_KEY: is_demo_mode(),
        DEMO_AI_KEY: use_demo_ai() if is_demo_mode() else get_setting_bool(DEMO_AI_KEY),
        DEMO_DASHBOARD_KEY: (
            use_demo_dashboard() if is_demo_mode() else get_setting_bool(DEMO_DASHBOARD_KEY)
        ),
        DEMO_PREDICTION_KEY: (
            use_demo_prediction() if is_demo_mode() else get_setting_bool(DEMO_PREDICTION_KEY)
        ),
        DEMO_SUSTAINABILITY_KEY: (
            use_demo_sustainability()
            if is_demo_mode()
            else get_setting_bool(DEMO_SUSTAINABILITY_KEY)
        ),
        DEMO_MARKETPLACE_KEY: (
            use_demo_marketplace() if is_demo_mode() else get_setting_bool(DEMO_MARKETPLACE_KEY)
        ),
    }


def get_stored_demo_settings() -> dict[str, bool]:
    """Formda gösterilecek değerler: DB kaydı yoksa env/default."""
    return {
        DEMO_MODE_KEY: is_demo_mode(),
        DEMO_AI_KEY: get_setting_bool(DEMO_AI_KEY, default=False),
        DEMO_DASHBOARD_KEY: get_setting_bool(DEMO_DASHBOARD_KEY, default=False),
        DEMO_PREDICTION_KEY: get_setting_bool(DEMO_PREDICTION_KEY, default=False),
        DEMO_SUSTAINABILITY_KEY: get_setting_bool(DEMO_SUSTAINABILITY_KEY, default=False),
        DEMO_MARKETPLACE_KEY: get_setting_bool(DEMO_MARKETPLACE_KEY, default=False),
    }


def save_demo_settings(
    values: dict[str, Any],
    *,
    admin_id: int | None = None,
    log_changes: bool = True,
) -> list[str]:
    """
    Demo ayarlarını kalıcı olarak yazar.
    Dönüş: audit'e yazılan aksiyon etiketleri.
    """
    from services.audit import log_admin_action

    if admin_id is None and current_user.is_authenticated:
        admin_id = current_user.id

    pending_logs: list[tuple[str, str, bool, bool]] = []
    now = utc_now()

    for key in DEMO_SETTING_KEYS:
        if key not in values:
            continue
        new_bool = bool(values[key])
        old_raw = _db_value(key)
        if old_raw is None and key == DEMO_MODE_KEY:
            old_bool = _env_demo_mode()
        else:
            old_bool = _parse_bool(old_raw) if old_raw is not None else False

        row = SystemSetting.query.filter_by(key=key).first()
        if row is None:
            row = SystemSetting(key=key, value="true" if new_bool else "false")
            db.session.add(row)
        else:
            row.value = "true" if new_bool else "false"
        row.updated_at = now
        row.updated_by_id = admin_id

        if log_changes and old_bool != new_bool:
            enabled_label, disabled_label = _AUDIT_LABELS[key]
            action = enabled_label if new_bool else disabled_label
            pending_logs.append((action, key, old_bool, new_bool))

    db.session.commit()

    logged: list[str] = []
    for action, key, old_bool, new_bool in pending_logs:
        log_admin_action(
            action,
            target="demo_settings",
            detail=f"{key}={new_bool}",
            old_value=str(old_bool).lower(),
            new_value=str(new_bool).lower(),
            admin_id=admin_id,
        )
        logged.append(action)
    return logged
