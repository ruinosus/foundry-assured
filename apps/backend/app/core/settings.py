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
    # Agentic retrieval (Foundry IQ) queries this Knowledge Base, which wraps the
    # cockpit-docbundles-ks knowledge source / index — no index name needed here.
    cockpit_search_knowledge_base: str = "cockpit-kb"
    # The index behind the knowledge source — the ACL stamping/trim operate on it.
    cockpit_search_index: str = "cockpit-docbundles-ks-index"
    cockpit_storage_container: str = "cockpit-corpus"

    # --- Phase 4: document-level access control (access follows the source) ---
    # A document's access = the group(s) that can read its SOURCE — arbitrary groups
    # (a GitHub team, an ADLS ACL group, a SharePoint group), NOT fixed tiers. The
    # mechanism stamps whatever groups the data declares per document and trims by the
    # caller's Entra identity. There is NO classification logic in code.
    #
    # cockpit_acl_group_map: the tenant's group NAME → Entra object-ID (env pairs
    #   "eng-pricing:<guid>,eng-platform:<guid>"). Manifests/classification carry NAMES;
    #   this resolves them to IDs. Values that are already GUIDs pass through.
    cockpit_acl_group_map: str = ""
    # Path to the owner's per-document access map (JSON: {document-key: [group-name,…]}),
    # external + gitignored like the corpus. Used when the bundle manifests don't already
    # carry `groups` (wiki_builder writes those by inheriting the repo's read teams).
    cockpit_acl_classification: str = ""
    # Groups for documents with NO declared access — empty = fail-closed (nobody sees).
    cockpit_acl_default_groups: str = ""
    # Back-compat: the three demo groups also seed the name→id map (public/internal/
    # confidential). Real tenants use cockpit_acl_group_map with their own group names.
    cockpit_acl_public_group: str = ""
    cockpit_acl_internal_group: str = ""
    cockpit_acl_confidential_group: str = ""

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
