"""Ulusal Karar Destek Merkezi — PDF rapor çıktısı."""

from __future__ import annotations

import io

from utils import utc_now


def export_decision_support_pdf(center: dict, report_type: str = "full") -> tuple[bytes, str]:
    """report_type: weekly | monthly | full"""
    report_type = (report_type or "full").lower()
    if report_type not in ("weekly", "monthly", "full"):
        report_type = "full"

    ts = utc_now().strftime("%Y%m%d_%H%M")
    filename = f"karar_destek_{report_type}_{ts}.pdf"
    ai = center.get("ai") or {}
    kpi = center.get("kpi") or {}
    risk = center.get("risk_analysis") or {}
    weekly = center.get("weekly_report") or {}
    monthly = center.get("monthly_report") or {}

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        from services.pdf_fonts import get_pdf_styles, table_font_commands

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = get_pdf_styles()
        titles = {
            "weekly": "Haftalık Ulusal Karar Destek Raporu",
            "monthly": "Aylık Ulusal Karar Destek Raporu",
            "full": "Ulusal Karar Destek Merkezi — Tam Rapor",
        }
        story = [
            Paragraph(f"AtıkPort — {titles[report_type]}", styles["Title"]),
            Spacer(1, 6),
            Paragraph(f"Oluşturulma: {utc_now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
            Spacer(1, 10),
        ]

        if ai.get("overview"):
            story.append(Paragraph("AI Özeti", styles["Heading2"]))
            story.append(Paragraph(ai["overview"], styles["Normal"]))
            story.append(Spacer(1, 8))

        story.append(Paragraph("Ulusal KPI", styles["Heading2"]))
        kpi_rows = [
            ["Metrik", "Değer"],
            ["Aktif belediye", str(kpi.get("aktif_belediye", ""))],
            ["Aktif kurum", str(kpi.get("aktif_kurum", ""))],
            ["Vatandaş", str(kpi.get("vatandas_sayisi", ""))],
            ["Katılım %", str(kpi.get("vatandas_katilim_orani", ""))],
            ["Geri kazanım kg", str(kpi.get("toplam_geri_kazanim_kg", ""))],
            ["CO₂ kg", str(kpi.get("co2_tasarrufu_kg", ""))],
        ]
        t = Table(kpi_rows, colWidths=[220, 160])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            *table_font_commands(size=9),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

        def _period_section(title, snap, narrative_key):
            story.append(Paragraph(title, styles["Heading2"]))
            m = snap.get("metrics") or {}
            ch = snap.get("change_pct") or {}
            story.append(Paragraph(
                f"İlan: {m.get('ilan')} (%{ch.get('ilan', 0)}) · "
                f"Teslim: {m.get('teslim')} (%{ch.get('teslim', 0)}) · "
                f"CO₂: {m.get('co2e_kg', 0):.1f} kg (%{ch.get('co2e_kg', 0)})",
                styles["Normal"],
            ))
            for line in ai.get(narrative_key) or []:
                story.append(Paragraph(f"• {line}", styles["Normal"]))
            story.append(Spacer(1, 10))

        if report_type in ("weekly", "full"):
            _period_section("Haftalık Rapor", weekly, "weekly_narrative")
        if report_type in ("monthly", "full"):
            _period_section("Aylık Rapor", monthly, "monthly_narrative")

        if report_type == "full":
            story.append(Paragraph("Risk Analizi", styles["Heading2"]))
            story.append(Paragraph(
                f"Seviye: {risk.get('level')} · Yüksek riskli belediye: "
                f"{risk.get('riskli_belediye_sayisi', 0)}",
                styles["Normal"],
            ))
            for fnd in risk.get("findings") or ai.get("risk_narrative") or []:
                story.append(Paragraph(f"• {fnd}", styles["Normal"]))
            story.append(Spacer(1, 10))

            story.append(Paragraph("Yeni Kampanya Önerileri", styles["Heading2"]))
            for c in center.get("campaigns") or []:
                story.append(Paragraph(
                    f"<b>{c.get('title')}</b> [{c.get('priority')}] — {c.get('description')}",
                    styles["Normal"],
                ))
            story.append(Spacer(1, 10))

            story.append(Paragraph("Belediye Karşılaştırmaları", styles["Heading2"]))
            cmp_rows = [["Belediye", "İl", "Puan", "Gelişim %"]]
            for r in (center.get("municipality_comparisons") or {}).get("top") or []:
                cmp_rows.append([
                    str(r.get("belediye_adi", ""))[:32],
                    str(r.get("il", "")),
                    str(r.get("puan", "")),
                    str(r.get("gelisim_yuzde", "")),
                ])
            tc = Table(cmp_rows, repeatRows=1, colWidths=[160, 80, 50, 60])
            tc.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#134e4a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                *table_font_commands(size=8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ]))
            story.append(tc)
            story.append(Spacer(1, 10))

            story.append(Paragraph("Kategori Değişimleri", styles["Heading2"]))
            for s in ((center.get("category_shifts") or {}).get("all") or [])[:8]:
                story.append(Paragraph(
                    f"• {s.get('kategori')}: {s.get('previous')} → {s.get('current')} "
                    f"(%{s.get('change_pct')})",
                    styles["Normal"],
                ))
            story.append(Spacer(1, 10))

            story.append(Paragraph("Vatandaş Katılım Eğilimleri", styles["Heading2"]))
            part = center.get("participation_trends") or {}
            story.append(Paragraph(
                f"Trend: {part.get('trend')} · Değişim %{part.get('change_pct')}",
                styles["Normal"],
            ))
            story.append(Spacer(1, 10))

            story.append(Paragraph("Bakanlık Aksiyon Önerileri", styles["Heading2"]))
            for a in center.get("ministry_actions") or []:
                story.append(Paragraph(
                    f"<b>{a.get('title')}</b> [{a.get('priority')}] — {a.get('detail')}",
                    styles["Normal"],
                ))

        doc.build(story)
        return buf.getvalue(), filename
    except ImportError:
        lines = [
            f"AtikPort Karar Destek — {report_type}",
            ai.get("overview") or "",
            f"Risk: {risk.get('level')}",
        ]
        for a in center.get("ministry_actions") or []:
            lines.append(f"* {a.get('title')}: {a.get('detail')}")
        return "\n".join(lines).encode("utf-8"), filename.replace(".pdf", ".txt")
