"""PDF DejaVu / Türkçe karakter regresyon testleri."""

from __future__ import annotations

import io
from pathlib import Path

TR_CHARS = "çğıİöşüÇĞİÖŞÜ"
TR_SAMPLE = "Şğİiçöü ĞÜŞIı ÇÖ AtıkPort Belediye Sürdürülebilirlik"


def test_dejavu_font_files_present():
    root = Path(__file__).resolve().parents[1] / "static" / "fonts"
    for name in (
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
    ):
        path = root / name
        assert path.is_file(), f"eksik font: {path}"
        assert path.stat().st_size > 10_000


def test_dejavu_cmap_covers_turkish():
    from fontTools.ttLib import TTFont

    from services.pdf_fonts import resolve_font_path

    for filename in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        cmap = TTFont(str(resolve_font_path(filename))).getBestCmap()
        missing = [ch for ch in TR_CHARS if ord(ch) not in cmap]
        assert not missing, f"{filename} eksik glifler: {missing}"


def test_register_and_styles_use_dejavu():
    from reportlab.pdfbase import pdfmetrics

    from services.pdf_fonts import (
        FONT_BOLD,
        FONT_REGULAR,
        get_pdf_styles,
        register_pdf_fonts,
    )

    fonts = register_pdf_fonts()
    assert fonts["regular"] == FONT_REGULAR
    assert pdfmetrics.stringWidth(TR_SAMPLE, FONT_REGULAR, 12) > 0
    assert pdfmetrics.stringWidth(TR_SAMPLE, FONT_BOLD, 12) > 0

    styles = get_pdf_styles()
    for name in ("Title", "Heading1", "Heading2", "Heading3", "Normal", "Caption", "Footer"):
        assert styles[name].fontName in (FONT_REGULAR, FONT_BOLD)
        assert "Helvetica" not in styles[name].fontName
        assert "Times" not in styles[name].fontName
        assert "Courier" not in styles[name].fontName


def test_probe_pdf_embeds_dejavu_not_helvetica():
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from services.pdf_fonts import FONT_REGULAR, get_pdf_styles, table_font_commands

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = get_pdf_styles()
    story = [
        Paragraph(f"AtıkPort — {TR_SAMPLE}", styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"<b>Kalın:</b> {TR_CHARS}", styles["Normal"]),
        Paragraph(f"<i>İtalik:</i> {TR_CHARS}", styles["Normal"]),
        Spacer(1, 8),
        Paragraph("Başlık ĞÜŞİÇÖ", styles["Heading2"]),
    ]
    table = Table(
        [["Şehir", "Ölçüm"], ["İstanbul", "çığ"], ["Eskişehir", "öğün"]],
        colWidths=[120, 120],
    )
    table.setStyle(TableStyle([*table_font_commands(size=10)]))
    story.append(table)
    doc.build(story)
    data = buf.getvalue()
    assert data[:4] == b"%PDF"
    assert b"DejaVu" in data
    # Gövde metni Helvetica kullanmamalı
    assert b"/F1" in data or b"DejaVu" in data
    # Font dosyası gömülü olmalı
    assert b"FontFile2" in data or b"/FontFile" in data


def test_sustainability_pdf_turkish(app):
    from services.sustainability_pdf import export_sustainability_pdf

    dashboard = {
        "current": {
            "belediye_adi": "Şişli Belediyesi",
            "il": "İstanbul",
            "puan": 81.5,
            "grade": "B",
            "criteria": [
                {"label": "Geri dönüşüm", "score": 80, "weight": 0.2, "weighted": 16},
                {"label": "Çevre eğitimi", "score": 70, "weight": 0.1, "weighted": 7},
            ],
        },
        "leaderboard": [
            {"sira": 1, "belediye_adi": "Çankaya", "il": "Ankara", "puan": 90, "grade": "A"},
        ],
        "province_ranking": [
            {"sira": 1, "il": "Eskişehir", "puan": 88, "grade": "A", "belediye_sayisi": 3},
        ],
        "history": {
            "trend": "yükseliş",
            "change_pct": 4.2,
            "series": [{"ay": "2026-01", "puan": 80, "teslim_orani": 70, "geri_donusum": 55, "co2e_kg": 12}],
        },
        "similar_municipalities": [],
        "rankings": {"turkey": {"sira": 3, "toplam": 15}, "il_belediye": {"sira": 1, "toplam": 2, "il": "İstanbul"}},
        "comparison": {"message": "Türkiye ortalamasının üzerinde (çığır açan)."},
    }
    report = {
        "summary": "Şehir sürdürülebilirlik göstergeleri güçlendi.",
        "strengths": ["Yüksek geri dönüşüm"],
        "improvements": ["Organik atık ayrıştırma"],
        "recommendations": ["İlçe bazlı kampanya"],
        "expected_gains": "CO₂ ve katılım artışı",
    }
    with app.app_context():
        data, filename = export_sustainability_pdf(dashboard, suggestions=[], report=report)
    assert filename.endswith(".pdf")
    assert data[:4] == b"%PDF"
    assert b"DejaVu" in data


def test_decision_support_pdf_turkish(app):
    from services.decision_support_pdf import export_decision_support_pdf

    center = {
        "ai": {
            "overview": "Ulusal özet: İstanbul ve Eskişehir öne çıkıyor.",
            "weekly_narrative": ["Haftalık teslim oranı yükseldi."],
            "monthly_narrative": ["Aylık katılım güçlendi."],
            "risk_narrative": ["Çevre baskısı orta seviyede."],
        },
        "kpi": {
            "aktif_belediye": 15,
            "aktif_kurum": 40,
            "vatandas_sayisi": 1000,
            "vatandas_katilim_orani": 62.5,
            "toplam_geri_kazanim_kg": 1200,
            "co2_tasarrufu_kg": 450,
        },
        "risk_analysis": {"level": "orta", "riskli_belediye_sayisi": 2, "findings": ["Yoğunluk: Şişli"]},
        "weekly_report": {"metrics": {"ilan": 10, "teslim": 8, "co2e_kg": 12.5}, "change_pct": {"ilan": 2, "teslim": 1, "co2e_kg": 3}},
        "monthly_report": {"metrics": {"ilan": 40, "teslim": 30, "co2e_kg": 50.0}, "change_pct": {"ilan": 5, "teslim": 4, "co2e_kg": 6}},
        "campaigns": [{"title": "Çevre Haftası", "priority": "yüksek", "description": "Şehir çapında bilinçlendirme"}],
        "municipality_comparisons": {
            "top": [{"belediye_adi": "Çankaya", "il": "Ankara", "puan": 90, "gelisim_yuzde": 3.1}]
        },
        "category_shifts": {"all": [{"kategori": "Elektronik", "previous": 10, "current": 14, "change_pct": 40}]},
        "participation_trends": {"trend": "yükseliş", "change_pct": 2.5},
        "ministry_actions": [{"title": "İl koordinasyonu", "priority": "orta", "detail": "Eskişehir pilotu"}],
    }
    with app.app_context():
        data, filename = export_decision_support_pdf(center, report_type="full")
    assert filename.endswith(".pdf")
    assert data[:4] == b"%PDF"
    assert b"DejaVu" in data


def test_moderation_pdf_turkish(app):
    from services import moderation_export

    original = moderation_export._scope_data

    def _fake(scope: str):
        return (
            ["tur", "baslik", "kullanici"],
            [{"tur": "atik", "baslik": "Şişe ve yağ", "kullanici": "öğrenci_çığ"}],
        )

    moderation_export._scope_data = _fake  # type: ignore
    try:
        with app.app_context():
            data, filename = moderation_export.export_pdf("records")
        assert filename.endswith(".pdf")
        assert data[:4] == b"%PDF"
        assert b"DejaVu" in data
    finally:
        moderation_export._scope_data = original
