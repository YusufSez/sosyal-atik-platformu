"""Sustainability Scoring — PDF rapor."""

from __future__ import annotations

import io

from utils import utc_now


def export_sustainability_pdf(dashboard: dict, suggestions: list | None = None) -> tuple[bytes, str]:
    """Skor kartı + lider tablosu PDF (reportlab)."""
    from services.sustainability_ai import suggestion_cards_as_text

    current = dashboard.get("current") or {}
    leaders = dashboard.get("leaderboard") or []
    provinces = dashboard.get("province_ranking") or []
    tip_lines = suggestion_cards_as_text(suggestions or [])
    ts = utc_now().strftime("%Y%m%d_%H%M")
    filename = f"surdurulebilirlik_{ts}.pdf"

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("AtıkPort — Sustainability Scoring Engine", styles["Title"]),
            Spacer(1, 8),
            Paragraph(f"Oluşturulma: {utc_now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
            Spacer(1, 12),
        ]

        ad = current.get("belediye_adi") or current.get("il") or "Bölge"
        story.append(Paragraph(
            f"<b>{ad}</b> — Puan: {current.get('puan', '—')} / 100 "
            f"(Not: {current.get('grade', '—')})",
            styles["Heading2"],
        ))
        comparison = (dashboard.get("comparison") or {}).get("message")
        if comparison:
            story.append(Paragraph(comparison, styles["Normal"]))
            story.append(Spacer(1, 8))

        crit_rows = [["Kriter", "Puan", "Ağırlık", "Katkı"]]
        for c in current.get("criteria") or []:
            crit_rows.append([
                c.get("label", ""),
                str(c.get("score", "")),
                str(c.get("weight", "")),
                str(c.get("weighted", "")),
            ])
        t1 = Table(crit_rows, repeatRows=1, colWidths=[220, 60, 60, 60])
        t1.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdfa")]),
        ]))
        story.append(t1)
        story.append(Spacer(1, 16))

        if tip_lines:
            story.append(Paragraph("AI Önerileri", styles["Heading2"]))
            for tip in tip_lines[:8]:
                story.append(Paragraph(f"• {tip}", styles["Normal"]))
            story.append(Spacer(1, 12))

        story.append(Paragraph("Türkiye Lider Tablosu (İlk 15)", styles["Heading2"]))
        lead_rows = [["Sıra", "Belediye", "İl", "Puan", "Not"]]
        for row in leaders[:15]:
            lead_rows.append([
                str(row.get("sira", "")),
                str(row.get("belediye_adi", ""))[:40],
                str(row.get("il", "")),
                str(row.get("puan", "")),
                str(row.get("grade", "")),
            ])
        t2 = Table(lead_rows, repeatRows=1, colWidths=[40, 180, 90, 50, 40])
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#134e4a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ]))
        story.append(t2)
        story.append(Spacer(1, 16))

        story.append(Paragraph("İl Sıralaması", styles["Heading2"]))
        il_rows = [["Sıra", "İl", "Puan", "Not", "Belediye"]]
        for row in provinces[:20]:
            il_rows.append([
                str(row.get("sira", "")),
                str(row.get("il", "")),
                str(row.get("puan", "")),
                str(row.get("grade", "")),
                str(row.get("belediye_sayisi", "")),
            ])
        t3 = Table(il_rows, repeatRows=1, colWidths=[40, 140, 50, 40, 70])
        t3.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#115e59")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ]))
        story.append(t3)

        doc.build(story)
        return buf.getvalue(), filename
    except ImportError:
        lines = [
            "AtikPort Sustainability Scoring Engine",
            f"Puan: {current.get('puan')} Not: {current.get('grade')}",
            "",
        ]
        for c in current.get("criteria") or []:
            lines.append(f"- {c.get('label')}: {c.get('score')}")
        for tip in tip_lines:
            lines.append(f"* {tip}")
        return "\n".join(lines).encode("utf-8"), filename.replace(".pdf", ".txt")
