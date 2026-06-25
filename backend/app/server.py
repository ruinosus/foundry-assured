"""FastAPI server exposing the helpdesk workflow over the AG-UI protocol.

The workflow is exposed via a per-request factory (AgentFrameworkWorkflow with
workflow_factory) so each run is built with the signed-in user's On-Behalf-Of
credential and memory scope (Phase 3). Auth is enforced by FastAPI dependencies
(Entra ID JWT validation) when configured; otherwise it falls back to a single
shared identity so the app still boots locally.

CORS note: add_agent_framework_fastapi_endpoint accepts an allow_origins kwarg,
but its docstring marks it "not yet implemented" (verified in
agent-framework-ag-ui 1.0.0rc5), so we apply CORSMiddleware ourselves.
"""

from contextlib import asynccontextmanager

import uvicorn
from agent_framework_ag_ui import (
    AgentFrameworkWorkflow,
    add_agent_framework_fastapi_endpoint,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.concierge import _knowledge_configured, build_concierge_agent
from app.auth import auth_dependencies, azure_scheme
from app.settings import settings
from app.workflow.graph import build_helpdesk_workflow


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-load the Entra OpenID config so the first authenticated request is fast.
    if azure_scheme is not None:
        await azure_scheme.openid_config.load_config()
    yield


app = FastAPI(title="Foundry Helpdesk", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Expose over AG-UI. With a knowledge base wired, use the per-request workflow
# factory (Phase 2 steps + Phase 3 per-user OBO/memory). Without a KB, fall back
# to the single concierge agent so the app still boots.
if _knowledge_configured():
    add_agent_framework_fastapi_endpoint(
        app,
        agent=AgentFrameworkWorkflow(workflow_factory=build_helpdesk_workflow),
        path="/helpdesk",
        dependencies=auth_dependencies(),
    )
else:
    add_agent_framework_fastapi_endpoint(
        app, agent=build_concierge_agent(), path="/helpdesk"
    )


if __name__ == "__main__":
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=True)
