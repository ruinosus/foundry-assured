"""Platform-global application settings, loaded from environment / .env.

Per-tenant data-plane config (Foundry/Search/Storage pointers, ACL, memory store,
hosted agent) lives in ``app.modules.tenancy.internal.tenant`` and is read via ``tenant_config()``.
This module keeps only platform-global settings (auth, CORS, tenant-store wiring).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Nome do escopo delegado exposto pela app registration. Fonte ÚNICA: `entra_api_scope` o
#: compõe, `shared/auth.py` o anuncia no bearer scheme, e o MCP o exige no verifier. Três
#: cópias literais era o que havia antes, e nenhuma derivava das outras.
ENTRA_API_SCOPE_NAME = "access_as_user"


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
    # in TenantConfig (app.modules.tenancy.internal.tenant), read via tenant_config().
    mcp_enabled: bool = False
    mcp_learn_url: str = "https://learn.microsoft.com/api/mcp"

    # The LangGraph on-call domain's model (ADR-020). Azure OpenAI deployment name — that
    # runtime uses LangChain's own client, so it does not go through FoundryChatClient.
    oncall_model: str = "gpt-5-mini"
    # LangChain's Azure client wants the OpenAI-shaped endpoint, not the Foundry project one.
    # Read through settings (not os.environ) so a value in .env actually reaches the code —
    # pydantic-settings loads .env into the model, never into the process environment.
    azure_openai_endpoint: str = ""
    # Probed against the deployed resource, not guessed: 2026-05-01-preview returns 404 on
    # this account; 2025-04-01-preview and 2024-10-21 both return 200. An api-version that does
    # not exist fails as "Resource not found", which reads like a wrong endpoint and sends you
    # looking in the wrong place.
    azure_openai_api_version: str = "2025-04-01-preview"

    # Telemetry content capture (I-10). OFF by default and meant to stay off outside
    # debugging: ON lets prompts, messages and tool arguments reach span EVENTS (never
    # attributes), redacted. ACL-trimmed documents and approver identity are excluded
    # regardless. See app/shared/telemetry/content_policy.py.
    telemetry_capture_content: bool = False

    # Tenants permitted to self-onboard (CSV of tids) — controlled rollout. WE control this.
    onboarding_allowed_tids: str = ""

    @property
    def allowed_tids(self) -> set[str]:
        return {t.strip() for t in self.onboarding_allowed_tids.split(",") if t.strip()}

    # CORS origin for the local Next.js frontend
    frontend_origin: str = "http://localhost:3000"

    #: URL pública do SERVIDOR MCP (`apps/mcp`, ADR-027) — não deste backend. Vira o `resource`
    #: da metadata OAuth (RFC 9728), que é o que o cliente usa para descobrir onde se autenticar.
    #: `frontend_origin` NÃO serve: é a origem do frontend, outro host. O default é a porta 8001
    #: porque é nela que `apps/mcp` sobe em dev; era 8000 enquanto o `/mcp` morava no monolito.
    #: O campo continua aqui, no shared kernel, porque `apps/mcp` instala este pacote e lê as
    #: mesmas settings — uma segunda classe de settings lá seria a segunda lista de sempre.
    mcp_public_base_url: str = "http://localhost:8001"

    #: A CHAVE QUE ASSINA O ESTADO ENTRE AS RODADAS da decisão humana do MCP (SEP-2322) — o
    #: `request_state` que o servidor emite junto com a pergunta e o cliente devolve junto com a
    #: resposta do aprovador. Sem ela, o `request_state` seria selado com uma chave efêmera do
    #: processo: a pergunta feita por uma réplica não seria aceita de volta por outra (nem pela
    #: mesma depois de um restart), e a escrita ficaria intermitente.
    #:
    #: SEM VALOR DE EXEMPLO QUE FUNCIONE, aqui ou no `.env.example` (ADR-005): a chave vem do
    #: ambiente, e no ambiente publicado vem do cofre. Vazio é um modo SUPORTADO — a escrita fica
    #: indisponível com erro claro, o resto do servidor não muda. Presente e curta demais
    #: (< 32 bytes) é ERRO: o `AESGCMRequestStateCodec` recusa na construção e o app não sobe,
    #: que é o que separa "não configurado" de "configurado errado".
    #:
    #: Mora aqui, no shared kernel, pelo mesmo motivo de `mcp_public_base_url`: `apps/mcp`
    #: instala este pacote e lê estas settings. Ver `apps/mcp/mcp_app/request_state.py`.
    mcp_request_state_key: str = ""

    #: O ÚNICO ARMAZENAMENTO DURÁVEL DO SERVIDOR MCP, e ele serve DUAS peças da Fase 5 (T7): o
    #: backend das background tasks (SEP-2663, via `pydocket`) e o `session_state_store` do
    #: estado por usuário. Uma variável para as duas porque é UM recurso — o Azure Cache for
    #: Redis que `infra/containerapps.bicep` provisiona quando `deployRedis` é verdadeiro.
    #:
    #: VAZIA É O MODO DE REPOUSO, e não uma falha: sem ela as tasks não sobem (a busca continua
    #: síncrona, que é o comportamento de sempre) e a sessão cai no `MemoryStore()` de processo.
    #: A degradação é declarada, não descoberta — ver `mcp_app/tasks_backend.py` e
    #: `mcp_app/sessions.py`, e os gates que provam cada metade.
    #:
    #: Contém a chave de acesso do Redis, então nunca há valor de exemplo aqui nem no
    #: `.env.example` (ADR-005): no ambiente publicado ela chega como Container App secret.
    mcp_redis_url: str = ""

    @property
    def auth_enabled(self) -> bool:
        """OBO/Entra is active only when the API app registration is configured.

        When unset, the app falls back to DefaultAzureCredential (single-identity,
        Phase 2 behavior) so it still boots for local dev.
        """
        return bool(self.entra_tenant_id and self.entra_api_client_id)

    @property
    def entra_api_scope(self) -> str:
        return f"api://{self.entra_api_client_id}/{ENTRA_API_SCOPE_NAME}"


settings = PlatformSettings()
