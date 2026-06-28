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

from contextlib import asynccontextmanager

import uvicorn
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.cockpit import build_cockpit_agent, cockpit_configured
from app.agents.concierge import _knowledge_configured, build_concierge_agent
from app.agents.selfwiki import build_selfwiki_agent, selfwiki_configured
from app.api import api_router
from app.core.auth import auth_dependencies, azure_scheme
from app.core.settings import settings
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


app = FastAPI(title="Foundry Helpdesk", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# AG-UI workflow endpoint (registered on the app, not via a router). With a KB
# wired, the per-request factory streams the Phase 2 steps + Phase 3 OBO/memory;
# without one, fall back to the single concierge agent.
if _knowledge_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=OrderedAgentFrameworkWorkflow(workflow_factory=build_helpdesk_workflow),
        path="/helpdesk",
        dependencies=auth_dependencies(),
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
        agent=build_cockpit_agent(),
        path="/cockpit",
        dependencies=auth_dependencies(),
    )

# Third domain: the selfwiki expert, grounded in a deep-wiki generated from THIS repo's
# own source (the dogfood). Registered only once selfwiki-kb is ingested + configured.
if selfwiki_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=build_selfwiki_agent(),
        path="/selfwiki",
        dependencies=auth_dependencies(),
    )


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
