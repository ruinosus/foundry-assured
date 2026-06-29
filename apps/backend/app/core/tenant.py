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

    Illustrative subset; the file-split task adds the rest (storage, embedding, per-domain
    KBs, ACL, memory store, hosted agent) per the spec's field classification.
    """
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"


class _TenantEnv(BaseSettings):
    """Loads the per-tenant fields from .env (same env var names as today) for SingleTenant."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"

    def as_config(self) -> TenantConfig:
        return TenantConfig(
            foundry_project_endpoint=self.foundry_project_endpoint,
            foundry_model=self.foundry_model,
            azure_search_endpoint=self.azure_search_endpoint,
            azure_search_knowledge_base=self.azure_search_knowledge_base,
        )


class TenantConfigProvider(Protocol):
    def current(self) -> TenantConfig: ...


class SingleTenantConfigProvider:
    """self_hosted / dedicated — one config from .env. Identical to today."""

    def current(self) -> TenantConfig:
        return _TenantEnv().as_config()


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
