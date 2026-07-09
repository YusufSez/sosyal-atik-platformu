"""AI Health monitoring — istek kaydı ve dashboard metrikleri."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from constants import AI_MODERATION_MODEL_DEFAULT, AI_PROMPT_VERSION
from extensions import db
from helpers import GEMINI_TIMEOUT_MS
from models import AiModerasyonHealthLog
from utils import utc_now


def classify_ai_error(exc: Exception | None, error_msg: str | None = None) -> str:
    """Hata tipini sınıflandırır."""
    text = f"{error_msg or ''} {exc or ''}".lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "rate" in text and "limit" in text:
        return "rate_limit"
    if "429" in text:
        return "rate_limit"
    if exc is None and not error_msg:
        return "none"
    return "api_error"


def record_ai_request(
    *,
    model_name: str,
    success: bool,
    response_time_ms: int | None = None,
    request_type: str = "vision",
    error_type: str | None = None,
    retry_count: int = 0,
    prompt_version: str | None = None,
) -> None:
    """AI isteğini kaydeder; hata durumunda moderasyon akışını bozmaz."""
    try:
        kayit = AiModerasyonHealthLog(
            model_name=model_name[:80],
            prompt_version=(prompt_version or AI_PROMPT_VERSION)[:20],
            request_type=request_type[:30],
            success=success,
            response_time_ms=response_time_ms,
            error_type=error_type,
            retry_count=retry_count,
            created_at=utc_now(),
        )
        db.session.add(kayit)
        db.session.flush()
    except Exception:
        db.session.rollback()


def ai_health_stats() -> dict[str, Any]:
    """Dashboard AI Health kartı verileri."""
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    logs = AiModerasyonHealthLog.query.filter(
        AiModerasyonHealthLog.created_at >= today_start
    ).all()

    total = len(logs)
    successful = sum(1 for l in logs if l.success)
    failed = total - successful
    timeouts = sum(1 for l in logs if l.error_type == "timeout")
    retries = sum(l.retry_count or 0 for l in logs)
    rate_limits = sum(1 for l in logs if l.error_type == "rate_limit")

    times = [l.response_time_ms for l in logs if l.success and l.response_time_ms]
    avg_ms = round(sum(times) / len(times)) if times else 0

    latest_model = AI_MODERATION_MODEL_DEFAULT
    if logs:
        latest_model = logs[-1].model_name

    success_rate = (successful / total * 100) if total else 100.0
    healthy = success_rate >= 80 and rate_limits < 10

    return {
        "model_name": latest_model,
        "prompt_version": AI_PROMPT_VERSION,
        "healthy": healthy,
        "avg_response_time_ms": avg_ms,
        "timeout_ms": GEMINI_TIMEOUT_MS,
        "timeout_count": timeouts,
        "retry_count": retries,
        "today_requests": total,
        "successful": successful,
        "failed": failed,
        "rate_limit_count": rate_limits,
        "success_rate": round(success_rate, 1),
    }
