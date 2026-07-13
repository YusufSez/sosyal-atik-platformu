"""Sustainability Scoring — PDF rapor."""

from __future__ import annotations

import io

from utils import utc_now


def export_sustainability_pdf(
    dashboard: dict,
    suggestions: list | None = None,
    *,
    report: dict | None = None,
) -> tuple[bytes, str]:
    """Skor + radar kriterleri + geçmiş + sıralama + AI raporu PDF."""
    from services.sustainability_ai import suggestion_cards_as_text

    current = dashboard.get("current") or {}
    leaders = dashboard.get("leaderboard") or []
    provinces = dashboard.get("province_ranking") or []
    history = dashboard.get("history") or {}
    similar = dashboard.get("similar_municipalities") or []
    ranks = dashboard.get("rankings") or {}
    tip_lines = suggestion_cards_as_text(suggestions or [])
    report = report or {}
    ts = utc_now().strftime("%Y%m%d_%H%M")
    filename = f"surdurulebilirlik_{ts}.pdf"

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        from services.pdf_fonts import get_pdf_styles, table_font_commands

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = get_pdf_styles()
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
            story.append(Spacer(1, 6))

        tr = ranks.get("turkey") or {}
        ilr = ranks.get("il_belediye") or {}
        if tr.get("sira"):
            story.append(Paragraph(
                f"Türkiye sıralaması: #{tr['sira']} / {tr.get('toplam', '—')}",
                styles["Normal"],
            ))
        if ilr.get("sira"):
            story.append(Paragraph(
                f"İl sıralaması ({ilr.get('il') or ''}): #{ilr['sira']} / {ilr.get('toplam', '—')}",
                styles["Normal"],
            ))
        story.append(Spacer(1, 10))

        # Kategori puanları
        story.append(Paragraph("Kategori Puanları", styles["Heading2"]))
        crit_rows = [["Kriter", "Puan", "Ağırlık", "Katkı"]]
        for c in current.get("criteria") or dashboard.get("category_scores") or []:
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
            *table_font_commands(size=9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdfa")]),
        ]))
        story.append(t1)
        story.append(Spacer(1, 14))

        # Geçmiş değişim
        series = history.get("series") or []
        if series:
            story.append(Paragraph("Geçmiş Değişim", styles["Heading2"]))
            story.append(Paragraph(
                f"Trend: {history.get('trend', '—')} · Değişim: %{history.get('change_pct', '—')}",
                styles["Normal"],
            ))
            hist_rows = [["Ay", "Puan", "Teslim %", "Geri dönüşüm", "CO₂ kg"]]
            for s in series:
                hist_rows.append([
                    s.get("ay", ""),
                    str(s.get("puan", "")),
                    str(s.get("teslim_orani", "")),
                    str(s.get("geri_donusum", "")),
                    str(s.get("co2e_kg", "")),
                ])
            th = Table(hist_rows, repeatRows=1, colWidths=[70, 50, 70, 80, 70])
            th.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#115e59")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                *table_font_commands(size=8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ]))
            story.append(th)
            story.append(Spacer(1, 14))

        # Benzer belediyeler
        if similar:
            story.append(Paragraph("Benzer Belediyeler", styles["Heading2"]))
            sim_rows = [["Belediye", "İl", "Puan", "Fark"]]
            for s in similar[:8]:
                sim_rows.append([
                    str(s.get("belediye_adi", ""))[:36],
                    str(s.get("il", "")),
                    str(s.get("puan", "")),
                    str(s.get("puan_farki", "")),
                ])
            ts_table = Table(sim_rows, repeatRows=1, colWidths=[180, 90, 50, 50])
            ts_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                *table_font_commands(size=8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ]))
            story.append(ts_table)
            story.append(Spacer(1, 14))

        # AI değerlendirme raporu
        story.append(Paragraph("AI Değerlendirmesi", styles["Heading2"]))
        if report.get("summary"):
            story.append(Paragraph(report["summary"], styles["Normal"]))
            story.append(Spacer(1, 6))
        for title, key in (
            ("3 Güçlü Yön", "strengths"),
            ("3 Geliştirme Alanı", "improvements"),
            ("3 Öneri", "recommendations"),
        ):
            items = report.get(key) or []
            if items:
                story.append(Paragraph(title, styles["Heading3"]))
                for item in items:
                    story.append(Paragraph(f"• {item}", styles["Normal"]))
                story.append(Spacer(1, 6))
        if report.get("expected_gains"):
            story.append(Paragraph("Beklenen Kazanım", styles["Heading3"]))
            story.append(Paragraph(report["expected_gains"], styles["Normal"]))
            story.append(Spacer(1, 10))

        if tip_lines:
            story.append(Paragraph("AI Öneri Kartları", styles["Heading2"]))
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
            *table_font_commands(size=8),
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
            *table_font_commands(size=8),
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
            "AI Rapor:",
            str(report.get("summary") or ""),
        ]
        for s in report.get("strengths") or []:
            lines.append(f"+ {s}")
        for s in report.get("improvements") or []:
            lines.append(f"- {s}")
        for s in report.get("recommendations") or []:
            lines.append(f"* {s}")
        if report.get("expected_gains"):
            lines.append(f"Kazanım: {report['expected_gains']}")
        for c in current.get("criteria") or []:
            lines.append(f"- {c.get('label')}: {c.get('score')}")
        for tip in tip_lines:
            lines.append(f"* {tip}")
        return "\n".join(lines).encode("utf-8"), filename.replace(".pdf", ".txt")
