"""FastAPI app entrypoint.

Thin: creates the app, applies CORS, includes the HTTP routers (app/api), and
registers the multi-agent workflow over **AG-UI** at `/helpdesk` via a per-request
factory (so each run uses the signed-in user's On-Behalf-Of credential + memory
scope). Without a knowledge base, it falls back to the single concierge agent so
the app still boots. Business logic lives in services/ and the agents/ + workflow/
packages — keep this file about wiring only.

CORS note: add_agent_framework_fastapi_endpoint accepts an allow_origins kwarg, but
its docstring marks it "not yet implemented" (agent-framework-ag-ui 1.0.0rc5), so we
apply CORSMiddleware ourselves.
"""

from collections.abc import Callable
from contextlib import asynccontextmanager

import uvicorn
from agent_framework import Agent
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.cockpit import build_cockpit_agent, cockpit_configured
from app.agents.concierge import _knowledge_configured, build_concierge_agent
from app.agents.per_request import PerRequestAgent
from app.agents.platform import PerRequestPlatformAgent, platform_configured
from app.agents.selfwiki import build_selfwiki_agent, selfwiki_configured
from app.api import api_router
from app.core.auth import auth_dependencies, azure_scheme
from app.core.settings import settings
from app.core.tenant import require_domain
from app.services.hosted import aclose as hosted_aclose
from app.workflow.graph import build_helpdesk_workflow
from app.workflow.stream_fix import OrderedAgentFrameworkWorkflow


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.include_router(api_router)


def _domain_deps(domain_id: str) -> list:
    """Auth deps, plus (shared mode only) the per-tenant entitlement gate. In self_hosted/
    dedicated this is exactly auth_dependencies() — byte-identical to today."""
    deps = auth_dependencies()
    if settings.deployment_mode == "shared":
        deps = [*deps, Depends(require_domain(domain_id))]
    return deps


def _grounded_agent(agent_id: str, builder: Callable[[], Agent]) -> PerRequestAgent | Agent:
    """The serving object for a grounded (build-once) domain.

    self_hosted/dedicated: build eagerly at boot under the single-tenant config — byte-identical
    to today. shared: NO tenant is resolved at boot, so builder() (which reads tenant_config())
    must NOT run yet — wrap it in a PerRequestAgent proxy that builds per request, once the
    auth/entitlement deps have resolved THIS request's tenant. Mirrors the helpdesk workflow
    factory + PerRequestPlatformAgent pattern, generalized for the grounded domains.
    """
    if settings.deployment_mode == "shared":
        return PerRequestAgent(agent_id, builder)
    return builder()


# AG-UI workflow endpoint (registered on the app, not via a router). With a KB
# wired, the per-request factory streams the Phase 2 steps + Phase 3 OBO/memory;
# without one, fall back to the single concierge agent.
if _knowledge_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=OrderedAgentFrameworkWorkflow(workflow_factory=build_helpdesk_workflow),
        path="/helpdesk",
        dependencies=_domain_deps("helpdesk"),
    )
else:
    add_agent_framework_fastapi_endpoint(
        app, agent=build_concierge_agent(), path="/helpdesk"
    )

# Second domain: the Cockpit expert, grounded in the cockpit-kb (registered only
# when that KB is configured). Pure grounded Q&A — no workflow/HITL.
if cockpit_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=_grounded_agent("cockpit", build_cockpit_agent),
        path="/cockpit",
        dependencies=_domain_deps("cockpit"),
    )

# Third domain: the selfwiki expert, grounded in a deep-wiki generated from THIS repo's
# own source (the dogfood). Registered only once selfwiki-kb is ingested + configured.
if selfwiki_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=_grounded_agent("selfwiki", build_selfwiki_agent),
        path="/selfwiki",
        dependencies=_domain_deps("selfwiki"),
    )

# Fourth domain: the platform/ops concierge — tool-driven over the Microsoft first-party
# MCP servers (Learn public now; OBO servers as infra lands). The PerRequestPlatformAgent
# proxy rebuilds the agent on each run so tools are filtered under the caller's roles + OBO
# credential (NOT once at boot — that's the whole point of this domain).
if platform_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=PerRequestPlatformAgent(),
        path="/platform",
        dependencies=_domain_deps("platform"),
    )


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
