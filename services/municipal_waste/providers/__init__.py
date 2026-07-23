"""Belediye sağlayıcı paketı."""

from services.municipal_waste.providers.ibb import IbbMunicipalProvider
from services.municipal_waste.providers.konya import KonyaMunicipalProvider

__all__ = ["IbbMunicipalProvider", "KonyaMunicipalProvider"]
