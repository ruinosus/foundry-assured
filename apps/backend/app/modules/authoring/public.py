"""Catálogo factual para autoria, projetado sem persistir uma segunda fonte de verdade."""

from app.modules.authoring.internal.bundles import (
    BundleBlocked,
    BundleNotFound,
    BundleService,
)
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
from app.modules.authoring.internal.changesets import (
    ChangeSetConflict,
    ChangeSetNotFound,
    ChangeSetPreconditionFailed,
    ChangeSetRepository,
    ChangeSetScope,
    ChangeSetService,
    PostgresChangeSetRepository,
    SQLiteChangeSetRepository,
    StoredChangeSet,
    default_changeset_service,
)
from app.modules.authoring.internal.sources import default_sources
from app.modules.authoring.internal.validations import (
    SQLiteValidationReportRepository,
    StoredValidationReport,
    ValidationCheck,
    ValidationReportNotFound,
    ValidationService,
    ValidationTransitionBlocked,
    default_validation_service,
)

__all__ = [
    "BundleBlocked",
    "BundleNotFound",
    "BundleService",
    "CatalogSource",
    "ChangeSetConflict",
    "ChangeSetNotFound",
    "ChangeSetPreconditionFailed",
    "ChangeSetRepository",
    "ChangeSetScope",
    "ChangeSetService",
    "PostgresChangeSetRepository",
    "ResourceNotFound",
    "SQLiteChangeSetRepository",
    "SQLiteValidationReportRepository",
    "SnapshotStale",
    "SourceUnavailable",
    "StoredChangeSet",
    "StoredValidationReport",
    "ValidationCheck",
    "ValidationReportNotFound",
    "ValidationService",
    "ValidationTransitionBlocked",
    "catalog_page",
    "default_changeset_service",
    "default_sources",
    "default_validation_service",
    "resource_activity",
    "resource_detail",
    "resource_versions",
]
