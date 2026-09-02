"""Superfície pública do perfil de autoria que estende OKF v0.2."""

from app.modules.okf.internal.actors import (
    agent_actor,
    generated_block,
    human_actor,
    okf_timestamp,
    process_actor,
    verified_entry,
)
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
    "agent_actor",
    "copilot_allows",
    "generated_block",
    "human_actor",
    "migrate_legacy_manifest",
    "okf_timestamp",
    "parse_authoring_document",
    "parse_mcp_binding",
    "process_actor",
    "serialize_authoring_document",
    "spec_references",
    "verified_entry",
]
