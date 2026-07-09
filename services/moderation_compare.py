"""Prompt / analiz versiyon karşılaştırması."""

from __future__ import annotations

from typing import Any

COMPARE_FIELDS = (
    ("final_risk", "Risk"),
    ("confidence", "Confidence"),
    ("purpose", "Purpose"),
    ("category", "Category"),
    ("matched_rules", "Matched Rules"),
    ("positive_signals", "Positive Signals"),
    ("negative_signals", "Negative Signals"),
    ("reason", "Reason"),
    ("prompt_version", "Prompt Version"),
    ("model_name", "Model Name"),
    ("analysis_version", "Analysis Version"),
)


def _normalize_value(val: Any) -> Any:
    if isinstance(val, list):
        return sorted(str(x) for x in val)
    if isinstance(val, float):
        return round(val, 4)
    return val


def compare_analyses(old: dict, new: dict) -> dict[str, Any]:
    """İki analizi yan yana karşılaştırır; farkları işaretler."""
    rows: list[dict[str, Any]] = []
    for key, label in COMPARE_FIELDS:
        old_val = old.get(key)
        new_val = new.get(key)
        changed = _normalize_value(old_val) != _normalize_value(new_val)
        rows.append({
            "key": key,
            "label": label,
            "old": old_val,
            "new": new_val,
            "changed": changed,
        })
    return {
        "old_version": old.get("analysis_version"),
        "new_version": new.get("analysis_version"),
        "old_prompt": old.get("prompt_version"),
        "new_prompt": new.get("prompt_version"),
        "rows": rows,
        "has_changes": any(r["changed"] for r in rows),
    }


def latest_reanalyze_comparison(analiz_gecmisi: list[dict]) -> dict[str, Any] | None:
    """Son iki analiz versiyonunu karşılaştırır."""
    if len(analiz_gecmisi) < 2:
        return None
    current = analiz_gecmisi[0]
    previous = analiz_gecmisi[1]
    return compare_analyses(previous, current)
