"""Platform-global application settings, loaded from environment / .env.

Per-tenant data-plane config (Foundry/Search/Storage pointers, ACL, memory store,
hosted agent) lives in ``app.core.tenant`` and is read via ``tenant_config()``.
This module keeps only platform-global settings (auth, CORS, tenant-store wiring).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Deployment mode + tenant store (a later task wires DEPLOYMENT_MODE) ---
    deployment_mode: str = "self_hosted"
    tenant_store_table: str = "tenants"
    tenant_store_account_url: str = ""
    # "table" (default, production) | "memory" (DEV/CI only — ephemeral, lets shared mode boot
    # offline; never use in production).
    tenant_store_backend: str = "table"

    # Artifacts (HTML artifacts feature)
    artifact_store_backend: str = "table"       # "table" | "memory"
    artifact_store_account_url: str = ""         # ARTIFACT_STORE_ACCOUNT_URL
    artifact_table: str = "artifacts"            # ARTIFACT_TABLE
    artifact_blob_account_url: str = ""          # ARTIFACT_BLOB_ACCOUNT_URL
    artifact_container: str = "artifacts"        # ARTIFACT_CONTAINER
    artifact_max_html_bytes: int = 2_000_000     # 2 MB cap (defense-in-depth)

    # --- Phase 3: Entra ID + On-Behalf-Of (per-user identity) ---
    # Backend API app registration (the audience of incoming tokens).
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_api_client_secret: str = ""
    # Frontend SPA app registration (surfaced to the frontend env; not used here).
    entra_spa_client_id: str = ""

    # --- MCP integration (platform/ops domain) — PLATFORM-GLOBAL flags only ---
    # mcp_enabled is a deployment switch; mcp_learn_url is the public Learn endpoint (same for
    # all tenants). The per-tenant MCP fields (ADO org, GitHub PAT, self-hosted Azure URL) live
    # in TenantConfig (app.core.tenant), read via tenant_config().
    mcp_enabled: bool = False
    mcp_learn_url: str = "https://learn.microsoft.com/api/mcp"

    # Tenants permitted to self-onboard (CSV of tids) — controlled rollout. WE control this.
    onboarding_allowed_tids: str = ""

    @property
    def allowed_tids(self) -> set[str]:
        return {t.strip() for t in self.onboarding_allowed_tids.split(",") if t.strip()}

    # CORS origin for the local Next.js frontend
    frontend_origin: str = "http://localhost:3000"

    @property
    def auth_enabled(self) -> bool:
        """OBO/Entra is active only when the API app registration is configured.

        When unset, the app falls back to DefaultAzureCredential (single-identity,
        Phase 2 behavior) so it still boots for local dev.
        """
        return bool(self.entra_tenant_id and self.entra_api_client_id)

    @property
    def entra_api_scope(self) -> str:
        return f"api://{self.entra_api_client_id}/access_as_user"


settings = PlatformSettings()
