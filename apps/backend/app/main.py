"""FastAPI app entrypoint.

Thin: creates the app, applies CORS, includes the HTTP routers (app/api), and
registers every domain's live endpoint via `mount_domains(app)` (app/registry.py) —
one loop that dispatches by `kind` (workflow/grounded/tool). Business logic lives in
services/ and the agents/ + workflow/ packages — keep this file about wiring only.

CORS note: add_agent_framework_fastapi_endpoint accepts an allow_origins kwarg, but
its docstring marks it "not yet implemented" (agent-framework-ag-ui 1.0.0rc5), so we
apply CORSMiddleware ourselves.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.hosted.public import aclose as hosted_aclose
from app.modules.platform_ops.public import SERVERS
from app.modules.tenancy import public as tenancy
from app.registry import include_routers, mount_domains
from app.shared.auth import azure_scheme
from app.shared.settings import settings
from app.shared.telemetry import configured as telemetry_configured
from app.shared.telemetry import setup_telemetry

logger = logging.getLogger(__name__)

# Telemetry first, so the rest of boot happens inside it. Default is a no-op: with no exporter
# configured the app behaves exactly as it did (I-1). See app/shared/telemetry.
#
# Este passo lê SÓ variável de ambiente — nada de rede. O import de `app.main` acontece dentro
# de `tests/smoke/routes_snapshot_test`, que é gate offline: uma chamada ao Azure aqui tornaria
# um gate determinístico dependente de credencial. O caminho que fala com o Foundry mora no
# `lifespan`, que o teste não executa.
setup_telemetry()


def _telemetry_from_foundry() -> None:
    """Liga a exportação com a connection string que o PRÓPRIO projeto Foundry já guarda.

    POR QUE ISTO EXISTIA NO PAPEL E NÃO NO CÓDIGO. `app/shared/telemetry` documenta que o
    composition root deveria resolver a string ("the fallback stays with the caller"), porque o
    shared kernel não pode importar `tenancy` (import-linter). A metade documentada nunca foi
    escrita, então `setup_telemetry()` caía sempre no ramo no-op fora de produção — e o Foundry
    não mostrava token nenhum, não porque não meça, mas porque nada chegava até ele.

    O `infra/resources.bicep` já provisiona o Application Insights e o conecta ao projeto como
    connection de categoria `AppInsights`; `telemetry.get_application_insights_connection_string()`
    é a API oficial que devolve essa string. Nada disto é contador nosso: o `agent-framework`
    emite os spans `gen_ai.usage.*` sozinho, e o painel Monitor do portal lê deles.

    Silencioso ao falhar, e em nível INFO ao ligar: telemetria que derruba boot é pior que
    telemetria ausente. No modo `shared` não há tenant fora de requisição — lá a variável de
    ambiente é o caminho, porque a conexão é por stamp.
    """
    if telemetry_configured():
        return
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        with AIProjectClient(
            endpoint=tenancy.tenant_config().foundry_project_endpoint,
            credential=DefaultAzureCredential(),
        ) as projeto:
            conexao = projeto.telemetry.get_application_insights_connection_string()
    except Exception as exc:  # noqa: BLE001 — sem Azure, sem exportação; o app segue igual
        logger.info("telemetry: sem connection string do projeto Foundry (%s)", type(exc).__name__)
        return
    if conexao and setup_telemetry(connection_string=conexao):
        logger.info("telemetry: exportando para o Application Insights do projeto Foundry")


# Wire tenancy into the auth flow (ADR-017). This used to be an import-time side effect of
# app/core/auth.py; making it an explicit call is what lets the shared kernel stop importing a
# business module. It must run before the first request, so that `require_user` finds the
# post-authenticate hook registered. No-op outside shared.
#
# It used to say "before mount_domains(), which reads tenant_config()". That was true and was
# the bug: reading tenant config while mounting is what stopped shared mode from booting at
# all. mount_domains() now walks the static topology only — see registry.DOMAIN_KINDS.
tenancy.install()

# Break the core↔agents cycle (ADR-017 §the cycle): the MCP server catalog is platform data,
# and tenancy only needs the valid ids to validate a connection kind. The composition root is
# the one place allowed to know both, so it hands the ids over instead of tenancy importing
# the platform registry.
tenancy.set_server_catalog(server.id for server in SERVERS)

# MEDIR PASSA A SER PROPRIEDADE DE FALAR COM O MODELO, não de cada agente lembrar. Havia cinco
# construções de `FoundryChatClient` espalhadas pelos módulos, e o painel de ROI mostrou o preço:
# um domínio com token gravado e todos os outros com zero, porque só um caminho se lembrava. Agora
# existe uma fábrica (`foundry.chat_client`) e ela carrega este middleware em todo cliente.
#
# A entrega vem daqui pelo mesmo motivo da linha acima: `conversations` importa `foundry`, então
# `foundry` importar `conversations` fecharia um ciclo que o import-linter recusa. O composition
# root é o único lugar que pode conhecer os dois.
from app.modules.conversations.public import usage_recorder
from app.modules.foundry.public import set_chat_middleware

set_chat_middleware(usage_recorder)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chamada de rede síncrona, uma vez, antes de servir — e não no import, pelo motivo escrito
    # acima. Sem exportador configurado por ambiente, é aqui que a exportação nasce.
    _telemetry_from_foundry()
    # Pre-load the Entra OpenID config so the first authenticated request is fast.
    if azure_scheme is not None:
        await azure_scheme.openid_config.load_config()
    yield
    await hosted_aclose()


app = FastAPI(title="Foundry Assured", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

include_routers(app)

# Every domain's live endpoint, mounted by ONE loop that dispatches by `kind`
# (workflow → helpdesk AG-UI; grounded → techdocs/selfwiki cited Q&A; tool → platform
# AG-UI). The hosted twins stay in app/api/chat.py.
mount_domains(app)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
