"""Per-tenant config resolution — the one seam that varies by DEPLOYMENT_MODE.

SingleTenant (self_hosted/dedicated) builds TenantConfig from .env = today's behavior.
MultiTenant (shared) resolves it from the per-request tenant set in require_user. The core
(agents, workflow) only ever calls tenant_config(); it never knows the mode.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Protocol

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class TenantConfig:
    """Per-tenant data-plane pointers (customer resources). ZERO secrets.

    Storage, embedding, per-domain KBs, ACL, memory store, and hosted agent — every
    field the core reads that varies by tenant.
    """
    # Foundry project endpoint, e.g. https://<project>.services.ai.azure.com/api/projects/<name>
    foundry_project_endpoint: str = ""
    # Model deployment name, e.g. gpt-5-mini
    foundry_model: str = "gpt-5-mini"

    # Foundry account OpenAI endpoint, e.g. https://<account>.openai.azure.com
    # Used by the knowledge base for embeddings + query planning.
    azure_ai_openai_endpoint: str = ""
    # Embedding deployment used to vectorize the corpus.
    foundry_embedding_model: str = "text-embedding-3-small"

    # --- Phase 1: Foundry IQ knowledge base (Azure AI Search) ---
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"

    # Storage holding the corpus (blob knowledge source).
    azure_storage_account: str = ""
    azure_storage_resource_id: str = ""
    azure_storage_container: str = "corpus"

    # --- Second domain: Cockpit expert (its own KB over the cockpit docbundles) ---
    cockpit_search_knowledge_base: str = "cockpit-kb"
    cockpit_search_index: str = "cockpit-docbundles-ks-index"
    cockpit_storage_container: str = "cockpit-corpus"

    # --- Third domain: selfwiki (this repo's own deep-wiki — dogfood) ---
    selfwiki_search_knowledge_base: str = ""
    selfwiki_search_index: str = "selfwiki-docbundles-ks-index"
    selfwiki_storage_container: str = "selfwiki-corpus"

    # --- Phase 4: document-level access control (access follows the source) ---
    cockpit_acl_group_map: str = ""
    cockpit_acl_classification: str = ""
    cockpit_acl_default_groups: str = ""
    cockpit_acl_public_group: str = ""
    cockpit_acl_internal_group: str = ""
    cockpit_acl_confidential_group: str = ""

    # Path to the aap-kb docbundles/ dir (internal Cockpit corpus).
    cockpit_docbundles_path: str = ""

    # --- Phase 3: Foundry memory store ---
    foundry_memory_store: str = "helpdesk-memory"

    # --- Phase 6: hosted agent (Foundry Agent Service) ---
    hosted_agent_name: str = "helpdesk-concierge"

    @property
    def acl_group_map(self) -> dict[str, str]:
        """Group NAME → Entra object-ID. cockpit_acl_group_map, plus the demo trio."""
        mapping: dict[str, str] = {}
        for name, gid in (
            ("public", self.cockpit_acl_public_group),
            ("internal", self.cockpit_acl_internal_group),
            ("confidential", self.cockpit_acl_confidential_group),
        ):
            if gid:
                mapping[name] = gid
        for pair in self.cockpit_acl_group_map.split(","):
            if ":" in pair:
                name, gid = pair.split(":", 1)
                mapping[name.strip()] = gid.strip()
        return mapping


class _TenantEnv(BaseSettings):
    """Loads the per-tenant fields from .env (same env var names as today) for SingleTenant."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    azure_ai_openai_endpoint: str = ""
    foundry_embedding_model: str = "text-embedding-3-small"
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"
    azure_storage_account: str = ""
    azure_storage_resource_id: str = ""
    azure_storage_container: str = "corpus"
    cockpit_search_knowledge_base: str = "cockpit-kb"
    cockpit_search_index: str = "cockpit-docbundles-ks-index"
    cockpit_storage_container: str = "cockpit-corpus"
    selfwiki_search_knowledge_base: str = ""
    selfwiki_search_index: str = "selfwiki-docbundles-ks-index"
    selfwiki_storage_container: str = "selfwiki-corpus"
    cockpit_acl_group_map: str = ""
    cockpit_acl_classification: str = ""
    cockpit_acl_default_groups: str = ""
    cockpit_acl_public_group: str = ""
    cockpit_acl_internal_group: str = ""
    cockpit_acl_confidential_group: str = ""
    cockpit_docbundles_path: str = ""
    foundry_memory_store: str = "helpdesk-memory"
    hosted_agent_name: str = "helpdesk-concierge"

    def as_config(self) -> TenantConfig:
        return TenantConfig(
            foundry_project_endpoint=self.foundry_project_endpoint,
            foundry_model=self.foundry_model,
            azure_ai_openai_endpoint=self.azure_ai_openai_endpoint,
            foundry_embedding_model=self.foundry_embedding_model,
            azure_search_endpoint=self.azure_search_endpoint,
            azure_search_knowledge_base=self.azure_search_knowledge_base,
            azure_storage_account=self.azure_storage_account,
            azure_storage_resource_id=self.azure_storage_resource_id,
            azure_storage_container=self.azure_storage_container,
            cockpit_search_knowledge_base=self.cockpit_search_knowledge_base,
            cockpit_search_index=self.cockpit_search_index,
            cockpit_storage_container=self.cockpit_storage_container,
            selfwiki_search_knowledge_base=self.selfwiki_search_knowledge_base,
            selfwiki_search_index=self.selfwiki_search_index,
            selfwiki_storage_container=self.selfwiki_storage_container,
            cockpit_acl_group_map=self.cockpit_acl_group_map,
            cockpit_acl_classification=self.cockpit_acl_classification,
            cockpit_acl_default_groups=self.cockpit_acl_default_groups,
            cockpit_acl_public_group=self.cockpit_acl_public_group,
            cockpit_acl_internal_group=self.cockpit_acl_internal_group,
            cockpit_acl_confidential_group=self.cockpit_acl_confidential_group,
            cockpit_docbundles_path=self.cockpit_docbundles_path,
            foundry_memory_store=self.foundry_memory_store,
            hosted_agent_name=self.hosted_agent_name,
        )


class TenantConfigProvider(Protocol):
    def current(self) -> TenantConfig: ...


class SingleTenantConfigProvider:
    """self_hosted / dedicated — one config from .env, static for the process. Identical to today.

    Parsed once at construction: single-tenant config doesn't change per request, and the workflow
    calls tenant_config() several times per run (triage/retrieve/resolve).
    """

    def __init__(self) -> None:
        self._cfg = _TenantEnv().as_config()

    def current(self) -> TenantConfig:
        return self._cfg


# The per-request resolved tenant record (set by require_user in multi-tenant mode).
# Holds Any to avoid importing tenant_store here (tenant_store imports TenantConfig from us).
_current_tenant: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "current_tenant", default=None
)


def set_current_tenant(record: object | None) -> None:
    _current_tenant.set(record)


def current_tenant_id() -> str | None:
    """The resolved tenant's tid, or None outside shared mode (used by memory_scope)."""
    rec = _current_tenant.get()
    return getattr(rec, "tid", None) if rec is not None else None


# The active provider, selected at boot (a later task wires DEPLOYMENT_MODE; default = SingleTenant).
_provider: TenantConfigProvider = SingleTenantConfigProvider()


def set_provider(provider: TenantConfigProvider) -> None:
    global _provider
    _provider = provider


def tenant_config() -> TenantConfig:
    """The current request's tenant config. The accessor every per-tenant call site uses."""
    return _provider.current()
