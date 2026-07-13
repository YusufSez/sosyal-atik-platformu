"""PDF Unicode font kaydı — DejaVu Sans (Türkçe karakter desteği).

Backend / API / rapor içeriği değişmez; yalnızca ReportLab font katmanı.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# ReportLab kayıt adları
FONT_REGULAR = "DejaVu"
FONT_BOLD = "DejaVu-Bold"
FONT_OBLIQUE = "DejaVu-Oblique"
FONT_BOLD_OBLIQUE = "DejaVu-BoldOblique"

_FONT_FILES = {
    FONT_REGULAR: "DejaVuSans.ttf",
    FONT_BOLD: "DejaVuSans-Bold.ttf",
    FONT_OBLIQUE: "DejaVuSans-Oblique.ttf",
    FONT_BOLD_OBLIQUE: "DejaVuSans-BoldOblique.ttf",
}

_REGISTERED = False


def _font_search_dirs() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    return [
        root / "static" / "fonts",
        root / "assets" / "fonts",
    ]


def resolve_font_path(filename: str) -> Path:
    for folder in _font_search_dirs():
        candidate = folder / filename
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(d) for d in _font_search_dirs())
    raise FileNotFoundError(
        f"PDF font bulunamadı: {filename} (aranan: {searched})"
    )


def register_pdf_fonts() -> dict[str, str]:
    """TTFont kayıtları — bir kez. Dönen dict: rol → ReportLab font adı."""
    global _REGISTERED
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if not _REGISTERED:
        for name, filename in _FONT_FILES.items():
            path = resolve_font_path(filename)
            pdfmetrics.registerFont(TTFont(name, str(path)))
        try:
            from reportlab.pdfbase.pdfmetrics import registerFontFamily

            registerFontFamily(
                FONT_REGULAR,
                normal=FONT_REGULAR,
                bold=FONT_BOLD,
                italic=FONT_OBLIQUE,
                boldItalic=FONT_BOLD_OBLIQUE,
            )
        except Exception:
            pass
        _REGISTERED = True

    return {
        "regular": FONT_REGULAR,
        "bold": FONT_BOLD,
        "oblique": FONT_OBLIQUE,
        "bold_oblique": FONT_BOLD_OBLIQUE,
    }


@lru_cache(maxsize=1)
def get_pdf_styles():
    """Unicode ParagraphStyle seti — Title / Heading / Normal / Caption / Footer."""
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    register_pdf_fonts()
    sample = getSampleStyleSheet()

    def clone(name: str, *, font: str, size: float, leading: float, **extra) -> ParagraphStyle:
        parent = sample[name]
        return ParagraphStyle(
            name=name,
            fontName=font,
            fontSize=size,
            leading=leading,
            textColor=parent.textColor,
            alignment=extra.pop("alignment", parent.alignment),
            spaceBefore=getattr(parent, "spaceBefore", 0),
            spaceAfter=getattr(parent, "spaceAfter", 0),
            **extra,
        )

    styles = getSampleStyleSheet()
    # Örnek stilleri DejaVu kopyalarıyla değiştir (Helvetica kullanma)
    for key, style in {
        "Normal": clone("Normal", font=FONT_REGULAR, size=10, leading=14),
        "BodyText": clone("BodyText", font=FONT_REGULAR, size=10, leading=14),
        "Title": clone("Title", font=FONT_BOLD, size=16, leading=20, alignment=TA_CENTER),
        "Heading1": clone("Heading1", font=FONT_BOLD, size=14, leading=18),
        "Heading2": clone("Heading2", font=FONT_BOLD, size=12, leading=16),
        "Heading3": clone("Heading3", font=FONT_BOLD, size=11, leading=14),
        "Heading4": clone("Heading4", font=FONT_BOLD, size=10, leading=13),
        "Heading5": clone("Heading5", font=FONT_BOLD, size=9, leading=12),
        "Heading6": clone("Heading6", font=FONT_BOLD, size=9, leading=12),
        "Italic": clone("Italic", font=FONT_OBLIQUE, size=10, leading=14),
        "Bullet": clone("Bullet", font=FONT_REGULAR, size=10, leading=14),
        "Definition": clone("Definition", font=FONT_REGULAR, size=10, leading=14),
        "Code": clone("Code", font=FONT_REGULAR, size=9, leading=12),
    }.items():
        styles.byName[key] = style
        if hasattr(styles, key):
            setattr(styles, key, style)

    caption = ParagraphStyle(
        name="Caption",
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
    )
    footer = ParagraphStyle(
        name="Footer",
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=10,
    )
    styles.add(caption)
    styles.add(footer)
    return styles


def table_font_commands(*, size: int = 9) -> list:
    """TableStyle için FONTNAME / FONTSIZE komutları."""
    register_pdf_fonts()
    return [
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), size),
    ]
