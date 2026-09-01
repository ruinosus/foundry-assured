"""Superfície pública do perfil de autoria que estende OKF v0.2."""

from app.modules.okf.internal.authoring import OPERATIONS, copilot_allows
from app.modules.okf.internal.bindings import McpBinding, parse_mcp_binding
from app.modules.okf.internal.catalog import AuthoringCatalog
from app.modules.okf.internal.changeset import (
    ChangeDecision,
    ChangeEvidence,
    ChangeGap,
    ChangeOperation,
    ChangeSetInvalid,
    DocumentDiff,
    FieldChange,
    OkfChangeSet,
)
from app.modules.okf.internal.envelope import (
    PROFILE_KEY,
    PROFILE_VERSIONS,
    PUBLICATION_STATES,
    AuthoringDocument,
    AuthoringInvalid,
    AuthoringReference,
    parse_authoring_document,
    serialize_authoring_document,
)
from app.modules.okf.internal.migration import (
    LEGACY_MANIFEST_FORMAT,
    migrate_legacy_manifest,
)
from app.modules.okf.internal.schemas import spec_references

__all__ = [
    "LEGACY_MANIFEST_FORMAT",
    "OPERATIONS",
    "PROFILE_KEY",
    "PROFILE_VERSIONS",
    "PUBLICATION_STATES",
    "AuthoringCatalog",
    "AuthoringDocument",
    "AuthoringInvalid",
    "AuthoringReference",
    "ChangeDecision",
    "ChangeEvidence",
    "ChangeGap",
    "ChangeOperation",
    "ChangeSetInvalid",
    "DocumentDiff",
    "FieldChange",
    "McpBinding",
    "OkfChangeSet",
    "copilot_allows",
    "migrate_legacy_manifest",
    "parse_authoring_document",
    "parse_mcp_binding",
    "serialize_authoring_document",
    "spec_references",
]
