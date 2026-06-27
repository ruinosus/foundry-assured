"""Application settings, loaded from environment / .env.

Env var names match what FoundryChatClient reads natively
(FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL), so the client can also pick them
up on its own — we surface them here for explicit wiring and validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Foundry project endpoint, e.g. https://<project>.services.ai.azure.com/api/projects/<name>
    foundry_project_endpoint: str = ""
    # Model deployment name, e.g. gpt-4.1-mini
    foundry_model: str = "gpt-4.1-mini"

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
    # The search index behind the cockpit knowledge source — queried directly in
    # semantic mode (agentic mode emits a per-turn tool call that breaks multi-turn).
    cockpit_search_index: str = "cockpit-docbundles-ks-index"
    cockpit_storage_container: str = "cockpit-corpus"
    # Path to the aap-kb docbundles/ dir (internal Cockpit corpus). Set via env
    # COCKPIT_DOCBUNDLES; the content is ingested to the cloud KB only, never committed.
    cockpit_docbundles_path: str = ""

    # --- Phase 3: Entra ID + On-Behalf-Of (per-user identity) ---
    # Backend API app registration (the audience of incoming tokens).
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_api_client_secret: str = ""
    # Frontend SPA app registration (surfaced to the frontend env; not used here).
    entra_spa_client_id: str = ""

    # --- Phase 3: Foundry memory store ---
    foundry_memory_store: str = "helpdesk-memory"

    # --- Phase 6: hosted agent (Foundry Agent Service) ---
    # Name of the deployed hosted agent, invoked via the Responses protocol.
    hosted_agent_name: str = "helpdesk-concierge"

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


settings = Settings()
