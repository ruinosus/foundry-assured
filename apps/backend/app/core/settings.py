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

    # --- Phase 3: Entra ID + On-Behalf-Of (per-user identity) ---
    # Backend API app registration (the audience of incoming tokens).
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_api_client_secret: str = ""
    # Frontend SPA app registration (surfaced to the frontend env; not used here).
    entra_spa_client_id: str = ""

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
