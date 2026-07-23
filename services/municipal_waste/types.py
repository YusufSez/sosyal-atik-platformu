from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NormalizedCenter:
    """Kaynak-bağımsız, UPSERT için normalize edilmiş atık merkezi kaydı."""

    name: str
    facility_type: str
    address: str
    district: str | None
    city: str
    latitude: float
    longitude: float
    image_url: str | None
    waste_types: list[str] = field(default_factory=list)
    description: str | None = None
    source: str = ""
    source_name: str = ""
    external_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "facility_type": self.facility_type,
            "address": self.address,
            "district": self.district,
            "city": self.city,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "image_url": self.image_url,
            "waste_types": list(self.waste_types),
            "description": self.description,
            "source": self.source,
            "source_name": self.source_name,
            "external_key": self.external_key,
        }


@dataclass(slots=True)
class SyncStats:
    source: str
    source_name: str = ""
    found: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    inactivated: int = 0
    errors: int = 0
    duration_ms: int = 0

    def log_lines(self) -> list[str]:
        label = self.source_name or self.source.replace("_", " ").title()
        return [
            f"{label} Sync Başladı...",
            f"{self.found} kayıt bulundu",
            f"{self.created} yeni kayıt eklendi",
            f"{self.updated} kayıt güncellendi",
            f"{self.skipped} kayıt pas geçildi",
            f"{self.inactivated} kayıt inactive yapıldı",
            f"{self.errors} hatalı kayıt",
            f"Süre: {self.duration_ms} ms",
            "Tamamlandı.",
        ]

    def summary_line(self) -> str:
        label = self.source_name or self.source
        return f"{label} .......... {self.found} kayıt"


@dataclass(slots=True)
class AggregateSyncStats:
    providers: list[SyncStats] = field(default_factory=list)

    @property
    def found(self) -> int:
        return sum(p.found for p in self.providers)

    @property
    def created(self) -> int:
        return sum(p.created for p in self.providers)

    @property
    def updated(self) -> int:
        return sum(p.updated for p in self.providers)

    @property
    def errors(self) -> int:
        return sum(p.errors for p in self.providers)

    @property
    def inactivated(self) -> int:
        return sum(p.inactivated for p in self.providers)

    def log_lines(self) -> list[str]:
        lines = [p.summary_line() for p in self.providers]
        lines.extend(
            [
                "",
                "Toplam",
                f"{self.found} kayıt",
                f"{self.created} yeni",
                f"{self.updated} güncellendi",
                f"{self.inactivated} inactive",
                f"{self.errors} hata",
            ]
        )
        return lines
