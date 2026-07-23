"""Belediye atık toplama noktası entegrasyonları (İBB, Konya, …)."""

from services.municipal_waste.registry import (
    get_provider,
    list_providers,
    register_provider,
    sync_all,
    sync_source,
)
from services.municipal_waste.types import AggregateSyncStats, NormalizedCenter, SyncStats

__all__ = [
    "AggregateSyncStats",
    "NormalizedCenter",
    "SyncStats",
    "get_provider",
    "list_providers",
    "register_provider",
    "sync_all",
    "sync_source",
]
