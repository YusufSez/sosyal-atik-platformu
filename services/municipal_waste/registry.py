from __future__ import annotations

import logging
import time
from typing import Any

from services.municipal_waste.base import MunicipalSourceProvider
from services.municipal_waste.providers.ibb import IbbMunicipalProvider
from services.municipal_waste.providers.konya import KonyaMunicipalProvider
from services.municipal_waste.types import AggregateSyncStats, SyncStats
from services.municipal_waste.upsert import upsert_centers

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[MunicipalSourceProvider]] = {
    IbbMunicipalProvider.source: IbbMunicipalProvider,
    KonyaMunicipalProvider.source: KonyaMunicipalProvider,
}


def register_provider(provider_cls: type[MunicipalSourceProvider]) -> None:
    """Yeni belediye sağlayıcısı kaydet (Ankara, İzmir, …)."""
    if not getattr(provider_cls, "source", None):
        raise ValueError("Provider.source zorunludur.")
    _PROVIDERS[provider_cls.source] = provider_cls


def list_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())


def get_provider(source: str) -> MunicipalSourceProvider:
    key = (source or "").strip().lower()
    try:
        return _PROVIDERS[key]()
    except KeyError as exc:
        raise KeyError(
            f"Bilinmeyen belediye kaynağı: {source!r}. "
            f"Kayıtlı kaynaklar: {', '.join(list_providers())}"
        ) from exc


def sync_source(source: str, **kwargs: Any) -> SyncStats:
    provider = get_provider(source)
    t0 = time.perf_counter()
    logger.info(
        "municipal_sync_start source=%s name=%s city=%s",
        provider.source,
        provider.source_name,
        provider.default_city,
    )
    centers = list(provider.load_centers(**kwargs))
    stats = upsert_centers(
        centers,
        source=provider.source,
        source_name=provider.source_name,
        stale_days=provider.stale_days,
    )
    stats.duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "municipal_sync_done source=%s found=%s created=%s updated=%s skipped=%s "
        "inactivated=%s errors=%s duration_ms=%s",
        provider.source,
        stats.found,
        stats.created,
        stats.updated,
        stats.skipped,
        stats.inactivated,
        stats.errors,
        stats.duration_ms,
    )
    for line in stats.log_lines():
        logger.info(line)
    return stats


def sync_all(**kwargs: Any) -> AggregateSyncStats:
    """Kayıtlı tüm provider'ları sırayla senkronize eder."""
    aggregate = AggregateSyncStats()
    logger.info("municipal_sync_all_start providers=%s", list_providers())
    for key in list_providers():
        # Dosya yolu yalnızca konya için anlamlı
        provider_kwargs = dict(kwargs)
        if key != "konya":
            provider_kwargs.pop("file_path", None)
        try:
            stats = sync_source(key, **provider_kwargs)
        except Exception:
            logger.exception("municipal_sync_all provider failed source=%s", key)
            failed = SyncStats(source=key, source_name=get_provider(key).source_name, errors=1)
            aggregate.providers.append(failed)
            continue
        aggregate.providers.append(stats)
    logger.info(
        "municipal_sync_all_done total_found=%s created=%s updated=%s inactivated=%s errors=%s",
        aggregate.found,
        aggregate.created,
        aggregate.updated,
        aggregate.inactivated,
        aggregate.errors,
    )
    for line in aggregate.log_lines():
        logger.info(line)
    return aggregate
