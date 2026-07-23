from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Sequence

from services.municipal_waste.types import NormalizedCenter

logger = logging.getLogger(__name__)

# Soft-delete: bu süreden uzun görülmeyen kayıtlar is_active=False olur
STALE_DAYS_DEFAULT = 90


class MunicipalSourceProvider(ABC):
    """Belediye açık veri / dosya kaynakları için ortak arayüz."""

    source: ClassVar[str]
    source_name: ClassVar[str]
    default_city: ClassVar[str]
    stale_days: ClassVar[int] = STALE_DAYS_DEFAULT

    @abstractmethod
    def load_centers(self, **kwargs) -> Sequence[NormalizedCenter]:
        """Normalize edilmiş merkez listesini üretir (ağ veya dosya)."""

    def describe(self) -> str:
        return f"{self.source_name} ({self.source})"

    def attach_metadata(self, center: NormalizedCenter) -> NormalizedCenter:
        """Provider metadata'sını kayda yazar (tek kaynak)."""
        from services.municipal_waste.text_utils import make_external_key

        center.source = self.source
        center.source_name = self.source_name
        if not center.city:
            center.city = self.default_city
        center.external_key = make_external_key(self.source, center.latitude, center.longitude)
        return center


def resolve_path(path: str | Path | None, *, default: Path) -> Path:
    if path is None:
        resolved = default
    else:
        resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Kaynak dosyası bulunamadı: {resolved}")
    return resolved
