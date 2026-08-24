"""Per-tenant config resolution — the one seam that varies by DEPLOYMENT_MODE.

SingleTenant (self_hosted/dedicated) builds TenantConfig from .env = today's behavior.
MultiTenant (shared) resolves it from the per-request tenant set in require_user. The core
(agents, workflow) only ever calls tenant_config(); it never knows the mode.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field
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

    # --- Second domain: TechDocs expert (its own KB over the techdocs docbundles) ---
    # techdocs_search_knowledge_base is the ACTIVE techdocs KB — flip this to cut the
    # domain over between the legacy azureBlob KB and the searchIndex KB below.
    # Task 2b: the searchIndex KB (techdocs-si-kb over techdocs-si-ks) is what lets the
    # native agentic retrieve honor the per-user ACL header (x-ms-query-source-authorization).
    techdocs_search_knowledge_base: str = "techdocs-kb"
    techdocs_search_index: str = "techdocs-docbundles-ks-index"
    techdocs_storage_container: str = "techdocs-corpus"
    # searchIndex-backed techdocs KB + its knowledge source (over the EXISTING ACL index).
    # Provisioned alongside the blob KB by ingest_docbundles; cutover = point
    # techdocs_search_knowledge_base at techdocs_searchindex_knowledge_base (fully reversible).
    techdocs_searchindex_knowledge_base: str = "techdocs-si-kb"
    techdocs_searchindex_knowledge_source: str = "techdocs-docbundles-si-ks"

    # --- Third domain: selfwiki (this repo's own deep-wiki — dogfood) ---
    # selfwiki_search_knowledge_base is the LEGACY azureBlob KB (selfwiki-kb). selfwiki has NO
    # per-user ACL (single-audience), so the searchIndex migration below is purely to unify it on
    # the native retrieve path (which hardcodes kind:searchIndex) — not a security concern.
    selfwiki_search_knowledge_base: str = ""
    selfwiki_search_index: str = "selfwiki-docbundles-ks-index"
    selfwiki_storage_container: str = "selfwiki-corpus"
    # searchIndex-backed selfwiki KB + its knowledge source (over the EXISTING selfwiki index).
    # Provisioned alongside the legacy blob KB (mirrors techdocs-si-kb); the registry points here so
    # the native retrieve's hardcoded kind:searchIndex matches. Reversible: repoint the registry back.
    selfwiki_searchindex_knowledge_base: str = "selfwiki-si-kb"
    selfwiki_searchindex_knowledge_source: str = "selfwiki-docbundles-si-ks"

    # --- Phase 4: document-level access control (access follows the source) — GENERIC (all domains) ---
    # Neutral ACL_* names (renamed off the techdocs product name — the old TECHDOCS_ACL_* env names
    # are gone). See the generic-config-naming-rename spec.
    acl_extra_group_map: str = ""   # extra "name:objectId,..." pairs beyond the named trio (env ACL_GROUP_MAP)
    acl_classification: str = ""
    acl_default_groups: str = ""
    acl_public_group: str = ""
    acl_internal_group: str = ""
    acl_confidential_group: str = ""

    # Path to a doc-bundle directory (the TechDocs corpus you point it at).
    techdocs_docbundles_path: str = ""

    # Entra group of app users (granted Foundry User to use the app, infra/resources.bicep). Doubles
    # as the selfwiki AUDIENCE: the self-wiki is readable by everyone with app access. Env APP_USERS_GROUP_ID.
    app_users_group_id: str = ""

    # --- Phase 3: Foundry memory store ---
    foundry_memory_store: str = "helpdesk-memory"

    # --- Phase 6: hosted agent (Foundry Agent Service) ---
    hosted_agent_name: str = "helpdesk-concierge"

    # D-runtime: the deployed platform hosted agent (Invocations protocol). Empty until deployed.
    platform_hosted_agent_name: str = "platform-concierge"
    techdocs_hosted_agent_name: str = "techdocs-expert"
    selfwiki_hosted_agent_name: str = "selfwiki-expert"

    # --- MCP integration: per-tenant fields (each tenant's own ADO org / GitHub PAT / self-
    # hosted Azure MCP URL). The platform-global mcp_enabled/mcp_learn_url stay in PlatformSettings.
    # DEPRECATED (C): the shared-mode build reads per-tenant Connections instead; kept for self-hosted back-compat
    mcp_ado_organization: str = ""
    mcp_github_pat: str = ""
    mcp_azure_url: str = ""

    @property
    def acl_group_map(self) -> dict[str, str]:
        """Group NAME → Entra object-ID. The named trio + acl_extra_group_map pairs."""
        mapping: dict[str, str] = {}
        for name, gid in (
            ("public", self.acl_public_group),
            ("internal", self.acl_internal_group),
            ("confidential", self.acl_confidential_group),
        ):
            if gid:
                mapping[name] = gid
        for pair in self.acl_extra_group_map.split(","):
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
    techdocs_search_knowledge_base: str = "techdocs-kb"
    techdocs_search_index: str = "techdocs-docbundles-ks-index"
    techdocs_storage_container: str = "techdocs-corpus"
    techdocs_searchindex_knowledge_base: str = "techdocs-si-kb"
    techdocs_searchindex_knowledge_source: str = "techdocs-docbundles-si-ks"
    selfwiki_search_knowledge_base: str = ""
    selfwiki_search_index: str = "selfwiki-docbundles-ks-index"
    selfwiki_storage_container: str = "selfwiki-corpus"
    selfwiki_searchindex_knowledge_base: str = "selfwiki-si-kb"
    selfwiki_searchindex_knowledge_source: str = "selfwiki-docbundles-si-ks"
    # ACL config — GENERIC (all domains). Env: ACL_PUBLIC_GROUP / ACL_INTERNAL_GROUP /
    # ACL_CONFIDENTIAL_GROUP / ACL_DEFAULT_GROUPS / ACL_CLASSIFICATION / ACL_GROUP_MAP.
    acl_extra_group_map: str = Field("", validation_alias="acl_group_map")  # env ACL_GROUP_MAP (raw "name:oid,..." pairs)
    acl_classification: str = ""
    acl_default_groups: str = ""
    acl_public_group: str = ""
    acl_internal_group: str = ""
    acl_confidential_group: str = ""
    techdocs_docbundles_path: str = ""
    app_users_group_id: str = ""
    foundry_memory_store: str = "helpdesk-memory"
    hosted_agent_name: str = "helpdesk-concierge"
    platform_hosted_agent_name: str = "platform-concierge"
    techdocs_hosted_agent_name: str = "techdocs-expert"
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
DOMAIN_IDS: tuple[str, ...] = ("helpdesk", "techdocs", "selfwiki", "platform")


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


def domain_enabled(domain_id: str) -> bool:
    """A regra de entitlement da ADR-010, sem vocabulário de transporte.

    Existe como função porque há DUAS superfícies que precisam dela — a dependency do FastAPI
    (`require_domain`) e o servidor MCP, que não passa por dependency nenhuma. Duas cópias da
    mesma regra divergiriam na primeira mudança, e a divergência não daria erro: serviria
    domínio não licenciado em silêncio numa das duas.
    """
    rec = _current_tenant.get()
    if rec is None:
        return False
    return domain_id in (getattr(rec, "enabled_domains", None) or ())


def require_domain(domain_id: str):
    """Shared-mode per-tenant entitlement gate (ADR-010). Fail-closed: 403 unless the
    resolved tenant's enabled_domains contains domain_id.

    Sub-depends on require_user so FastAPI resolves the tenant (sets _current_tenant)
    before this runs — ordering comes from the dependency graph, not list position.
    Imported lazily (factory call time = route setup) to avoid an import cycle at module load.
    """
    from fastapi import Depends, HTTPException

    from app.shared.auth import require_user

    async def _check(_user=Depends(require_user)) -> None:
        if not domain_enabled(domain_id):
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
