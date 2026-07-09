"""Moderasyon verilerini CSV / Excel / PDF olarak dışa aktarır."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from models import (
    Atik,
    IlanModerasyonAnaliz,
    IlanModerasyonKarar,
    IlanModerasyonTimeline,
    Kaynak,
    User,
)
from services.moderation_admin import dashboard_istatistikleri, moderasyon_listesi
from utils import utc_now

EXPORT_SCOPES = ("records", "timeline", "dashboard", "decisions")


def _records_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    result = moderasyon_listesi()
    items = result if isinstance(result, list) else result.items
    for item in items:
        rows.append({
            "tur": item.tur,
            "ilan_id": item.ilan_id,
            "baslik": item.baslik,
            "kullanici": item.kullanici,
            "tarih": item.tarih.isoformat() if item.tarih else "",
            "risk": item.risk_skoru,
            "spam": item.spam_score,
            "duplicate": item.duplicate_score,
            "status": item.moderation_status,
            "category": item.category,
            "purpose": item.purpose,
        })
    return rows


def _timeline_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ev in IlanModerasyonTimeline.query.order_by(IlanModerasyonTimeline.created_at.desc()).limit(5000).all():
        ilan_id = ev.kaynak_id or ev.atik_id
        rows.append({
            "tur": ev.tur,
            "ilan_id": ilan_id,
            "event_type": ev.event_type,
            "title": ev.title,
            "created_at": ev.created_at.isoformat() if ev.created_at else "",
        })
    return rows


def _dashboard_rows() -> list[dict[str, Any]]:
    stats = dashboard_istatistikleri()
    rows = [{"metric": k, "value": str(v)} for k, v in stats.items() if not isinstance(v, (dict, list))]
    return rows


def _decisions_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for k in IlanModerasyonKarar.query.order_by(IlanModerasyonKarar.decision_time.desc()).limit(5000).all():
        ilan_id = k.kaynak_id or k.atik_id
        admin = User.query.get(k.admin_user_id)
        rows.append({
            "tur": k.tur,
            "ilan_id": ilan_id,
            "ai_decision": k.ai_decision,
            "admin_decision": k.admin_decision,
            "match": k.decision_match,
            "override": k.override,
            "action": k.action_type,
            "admin": admin.username if admin else "",
            "time": k.decision_time.isoformat() if k.decision_time else "",
            "reason": (k.decision_reason or "")[:200],
        })
    return rows


def _scope_data(scope: str) -> tuple[list[str], list[dict[str, Any]]]:
    if scope == "records":
        rows = _records_rows()
        headers = list(rows[0].keys()) if rows else ["tur", "ilan_id", "baslik"]
    elif scope == "timeline":
        rows = _timeline_rows()
        headers = list(rows[0].keys()) if rows else ["tur", "event_type", "title"]
    elif scope == "dashboard":
        rows = _dashboard_rows()
        headers = ["metric", "value"]
    elif scope == "decisions":
        rows = _decisions_rows()
        headers = list(rows[0].keys()) if rows else ["tur", "ai_decision", "admin_decision"]
    else:
        raise ValueError(f"Geçersiz export scope: {scope}")
    return headers, rows


def export_csv(scope: str) -> tuple[bytes, str]:
    """CSV bytes ve dosya adı döndürür."""
    headers, rows = _scope_data(scope)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    ts = utc_now().strftime("%Y%m%d_%H%M")
    return buf.getvalue().encode("utf-8-sig"), f"moderasyon_{scope}_{ts}.csv"


def export_excel(scope: str) -> tuple[bytes, str]:
    """Excel bytes ve dosya adı."""
    try:
        from openpyxl import Workbook
    except ImportError:
        return export_csv(scope)

    headers, rows = _scope_data(scope)
    wb = Workbook()
    ws = wb.active
    ws.title = scope[:31]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    ts = utc_now().strftime("%Y%m%d_%H%M")
    return buf.getvalue(), f"moderasyon_{scope}_{ts}.xlsx"


def export_pdf(scope: str) -> tuple[bytes, str]:
    """PDF bytes ve dosya adı."""
    headers, rows = _scope_data(scope)
    ts = utc_now().strftime("%Y%m%d_%H%M")
    filename = f"moderasyon_{scope}_{ts}.pdf"

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        story = [
            Paragraph(f"AtıkPort Moderasyon Export — {scope}", styles["Title"]),
            Spacer(1, 12),
            Paragraph(f"Oluşturulma: {utc_now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
            Spacer(1, 12),
        ]
        if rows:
            data = [headers] + [[str(row.get(h, ""))[:80] for h in headers] for row in rows[:100]]
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ]))
            story.append(table)
        else:
            story.append(Paragraph("Kayıt bulunamadı.", styles["Normal"]))
        doc.build(story)
        return buf.getvalue(), filename
    except ImportError:
        text = f"AtikPort Moderasyon Export — {scope}\n\n"
        for row in rows[:200]:
            text += " | ".join(f"{h}: {row.get(h, '')}" for h in headers) + "\n"
        return text.encode("utf-8"), filename.replace(".pdf", ".txt")
