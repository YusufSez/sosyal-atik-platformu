"""Explainability — positive/negative signals."""

from __future__ import annotations

from typing import Any

POSITIVE_RULE_PREFIXES = ("purpose_",)
POSITIVE_RULES = frozenset({
    "purpose_detected",
    "recycling_context",
    "whitelist_material",
    "is_recyclable_flag",
    "risk_adjusted",
    "whitelist_applied",
})

NEGATIVE_RULES = frozenset({
    "motor_oil_warning",
    "inappropriate_content",
    "spam_detected",
    "duplicate_detected",
    "high_risk",
    "uygunsuz",
})


def compute_explainability_signals(sonuc: dict) -> tuple[list[str], list[str]]:
    """Pozitif ve negatif sinyalleri üretir."""
    positive: list[str] = []
    negative: list[str] = []
    seen: set[str] = set()

    def _add(target: list[str], label: str) -> None:
        if label not in seen:
            seen.add(label)
            target.append(label)

    for rule in sonuc.get("matched_rules") or []:
        if rule in POSITIVE_RULES or any(rule.startswith(p) for p in POSITIVE_RULE_PREFIXES):
            _add(positive, rule)
        elif rule in NEGATIVE_RULES:
            _add(negative, rule)

    if sonuc.get("whitelist_applied"):
        _add(positive, "whitelist_applied")
    if sonuc.get("is_recyclable"):
        _add(positive, "is_recyclable")
    if sonuc.get("uygunsuz"):
        _add(negative, "inappropriate_content")

    risk = int(sonuc.get("final_risk", sonuc.get("risk_skoru", 0)))
    if risk >= 70:
        _add(negative, "high_risk")
    elif risk <= 30:
        _add(positive, "low_risk")

    spam = sonuc.get("spam_score") or 0
    if spam >= 40:
        _add(negative, "spam_detected")
    dup = sonuc.get("duplicate_score") or 0
    if dup >= 50:
        _add(negative, "duplicate_detected")

    return positive, negative


def enrich_explainability_signals(sonuc: dict) -> dict:
    """sonuc dict'e positive_signals ve negative_signals ekler."""
    pos, neg = compute_explainability_signals(sonuc)
    out = dict(sonuc)
    out["positive_signals"] = pos
    out["negative_signals"] = neg
    return out


def explainability_from_analiz(analiz_dict: dict) -> dict[str, Any]:
    """Analiz dict'ten explainability paketi."""
    raw = analiz_dict or {}
    pos = raw.get("positive_signals")
    neg = raw.get("negative_signals")
    if pos is None or neg is None:
        pos, neg = compute_explainability_signals(raw)
    return {
        "matched_rules": raw.get("matched_rules") or [],
        "positive_signals": pos,
        "negative_signals": neg,
        "reason": raw.get("reason"),
        "confidence": raw.get("confidence"),
    }
