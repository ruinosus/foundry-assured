"""Catálogo factual para autoria, projetado sem persistir uma segunda fonte de verdade."""

from app.modules.authoring.internal.catalog import (
    CatalogSource,
    ResourceNotFound,
    SnapshotStale,
    SourceUnavailable,
    catalog_page,
    resource_activity,
    resource_detail,
    resource_versions,
)
from app.modules.authoring.internal.sources import default_sources

__all__ = [
    "CatalogSource",
    "ResourceNotFound",
    "SnapshotStale",
    "SourceUnavailable",
    "catalog_page",
    "default_sources",
    "resource_activity",
    "resource_detail",
    "resource_versions",
]
