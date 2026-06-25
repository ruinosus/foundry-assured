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

    # CORS origin for the local Next.js frontend
    frontend_origin: str = "http://localhost:3000"


settings = Settings()
