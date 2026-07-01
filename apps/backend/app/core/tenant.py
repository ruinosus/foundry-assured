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
    # cockpit_search_knowledge_base is the ACTIVE cockpit KB — flip this to cut the
    # domain over between the legacy azureBlob KB and the searchIndex KB below.
    # Task 2b: the searchIndex KB (cockpit-si-kb over cockpit-si-ks) is what lets the
    # native agentic retrieve honor the per-user ACL header (x-ms-query-source-authorization).
    cockpit_search_knowledge_base: str = "cockpit-kb"
    cockpit_search_index: str = "cockpit-docbundles-ks-index"
    cockpit_storage_container: str = "cockpit-corpus"
    # searchIndex-backed cockpit KB + its knowledge source (over the EXISTING ACL index).
    # Provisioned alongside the blob KB by ingest_cockpit; cutover = point
    # cockpit_search_knowledge_base at cockpit_searchindex_knowledge_base (fully reversible).
    cockpit_searchindex_knowledge_base: str = "cockpit-si-kb"
    cockpit_searchindex_knowledge_source: str = "cockpit-docbundles-si-ks"

    # --- Third domain: selfwiki (this repo's own deep-wiki — dogfood) ---
    # selfwiki_search_knowledge_base is the LEGACY azureBlob KB (selfwiki-kb). selfwiki has NO
    # per-user ACL (single-audience), so the searchIndex migration below is purely to unify it on
    # the native retrieve path (which hardcodes kind:searchIndex) — not a security concern.
    selfwiki_search_knowledge_base: str = ""
    selfwiki_search_index: str = "selfwiki-docbundles-ks-index"
    selfwiki_storage_container: str = "selfwiki-corpus"
    # searchIndex-backed selfwiki KB + its knowledge source (over the EXISTING selfwiki index).
    # Provisioned alongside the legacy blob KB (mirrors cockpit-si-kb); the registry points here so
    # the native retrieve's hardcoded kind:searchIndex matches. Reversible: repoint the registry back.
    selfwiki_searchindex_knowledge_base: str = "selfwiki-si-kb"
    selfwiki_searchindex_knowledge_source: str = "selfwiki-docbundles-si-ks"

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

    # D-runtime: the deployed platform hosted agent (Invocations protocol). Empty until deployed.
    platform_hosted_agent_name: str = "platform-concierge"
    cockpit_hosted_agent_name: str = "cockpit-expert"
    selfwiki_hosted_agent_name: str = "selfwiki-expert"

    # --- MCP integration: per-tenant fields (each tenant's own ADO org / GitHub PAT / self-
    # hosted Azure MCP URL). The platform-global mcp_enabled/mcp_learn_url stay in PlatformSettings.
    # DEPRECATED (C): the shared-mode build reads per-tenant Connections instead; kept for self-hosted back-compat
    mcp_ado_organization: str = ""
    mcp_github_pat: str = ""
    mcp_azure_url: str = ""

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
    cockpit_searchindex_knowledge_base: str = "cockpit-si-kb"
    cockpit_searchindex_knowledge_source: str = "cockpit-docbundles-si-ks"
    selfwiki_search_knowledge_base: str = ""
    selfwiki_search_index: str = "selfwiki-docbundles-ks-index"
    selfwiki_storage_container: str = "selfwiki-corpus"
    selfwiki_searchindex_knowledge_base: str = "selfwiki-si-kb"
    selfwiki_searchindex_knowledge_source: str = "selfwiki-docbundles-si-ks"
    cockpit_acl_group_map: str = ""
    cockpit_acl_classification: str = ""
    cockpit_acl_default_groups: str = ""
    cockpit_acl_public_group: str = ""
    cockpit_acl_internal_group: str = ""
    cockpit_acl_confidential_group: str = ""
    cockpit_docbundles_path: str = ""
    foundry_memory_store: str = "helpdesk-memory"
    hosted_agent_name: str = "helpdesk-concierge"
    platform_hosted_agent_name: str = "platform-concierge"
    cockpit_hosted_agent_name: str = "cockpit-expert"
    selfwiki_hosted_agent_name: str = "selfwiki-expert"
    # DEPRECATED (C): the shared-mode build reads per-tenant Connections instead; kept for self-hosted back-compat
    mcp_ado_organization: str = ""
    mcp_github_pat: str = ""
    mcp_azure_url: str = ""

    def as_config(self) -> TenantConfig:
        return TenantConfig(**{k: getattr(self, k) for k in TenantConfig.__dataclass_fields__})


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


class MultiTenantConfigProvider:
    """shared — the config of the tenant resolved for THIS request (set in require_user)."""

    def current(self) -> TenantConfig:
        rec = _current_tenant.get()
        if rec is None:
            raise RuntimeError("no tenant resolved for this request")
        return rec.data_plane  # type: ignore[attr-defined]


def set_current_tenant(record: object | None) -> None:
    _current_tenant.set(record)


def current_tenant_id() -> str | None:
    """The resolved tenant's tid, or None outside shared mode (used by memory_scope)."""
    rec = _current_tenant.get()
    return getattr(rec, "tid", None) if rec is not None else None


# The registered agent domains (shared mode mounts all; entitlement gates per tenant).
DOMAIN_IDS: tuple[str, ...] = ("helpdesk", "cockpit", "selfwiki", "platform")


# Per-tier domain entitlement (ADR-010 Open Q#3). Unknown/unset tier → all domains (non-breaking;
# the request-time require_domain gate stays fail-closed regardless of the seed).
TIER_DOMAINS: dict[str, tuple[str, ...]] = {
    "shared": DOMAIN_IDS,
    # "starter": illustrative only — not wired to any product tier yet (the ADR-010 hook).
    # Kept to exercise the non-trivial branch + the ⊆ DOMAIN_IDS subset test.
    "starter": ("helpdesk", "selfwiki"),
}


def domains_for_tier(tier: str | None) -> tuple[str, ...]:
    return TIER_DOMAINS.get(tier or "", DOMAIN_IDS)


def require_domain(domain_id: str):
    """Shared-mode per-tenant entitlement gate (ADR-010). Fail-closed: 403 unless the
    resolved tenant's enabled_domains contains domain_id.

    Sub-depends on require_user so FastAPI resolves the tenant (sets _current_tenant)
    before this runs — ordering comes from the dependency graph, not list position.
    Imported lazily (factory call time = route setup) to avoid an import cycle at module load.
    """
    from fastapi import Depends, HTTPException

    from app.core.auth import require_user

    async def _check(_user=Depends(require_user)) -> None:
        rec = _current_tenant.get()
        enabled = getattr(rec, "enabled_domains", None) or ()
        if rec is None or domain_id not in enabled:
            raise HTTPException(status_code=403, detail=f"domain '{domain_id}' not enabled for tenant")

    return _check


# The active provider, selected at boot (a later task wires DEPLOYMENT_MODE; default = SingleTenant).
_provider: TenantConfigProvider = SingleTenantConfigProvider()


def set_provider(provider: TenantConfigProvider) -> None:
    global _provider
    _provider = provider


def tenant_config() -> TenantConfig:
    """The current request's tenant config. The accessor every per-tenant call site uses."""
    return _provider.current()
