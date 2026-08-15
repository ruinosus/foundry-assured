"""FastAPI app entrypoint.

Thin: creates the app, applies CORS, includes the HTTP routers (app/api), and
registers every domain's live endpoint via `mount_domains(app)` (app/domains.py) —
one loop that dispatches by `kind` (workflow/grounded/tool). Business logic lives in
services/ and the agents/ + workflow/ packages — keep this file about wiring only.

CORS note: add_agent_framework_fastapi_endpoint accepts an allow_origins kwarg, but
its docstring marks it "not yet implemented" (agent-framework-ag-ui 1.0.0rc5), so we
apply CORSMiddleware ourselves.
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.mcp.registry import SERVERS
from app.api import api_router
from app.core import tenant_resolution, tenant_store
from app.domains import mount_domains
from app.services.hosted import aclose as hosted_aclose
from app.shared.auth import azure_scheme
from app.shared.settings import settings

# Wire tenancy into the auth flow (ADR-017). This used to be an import-time side effect of
# app/core/auth.py; making it an explicit call is what lets the shared kernel stop importing a
# business module. It MUST run before mount_domains(), which reads tenant_config() and would
# otherwise see the default SingleTenant provider in shared mode. No-op outside shared.
tenant_resolution.install()

# Break the core↔agents cycle (ADR-017 §the cycle): the MCP server catalog is platform data,
# and tenancy only needs the valid ids to validate a connection kind. The composition root is
# the one place allowed to know both, so it hands the ids over instead of tenancy importing
# the platform registry.
tenant_store.set_server_catalog(server.id for server in SERVERS)


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

# Every domain's live endpoint, mounted by ONE loop that dispatches by `kind`
# (workflow → helpdesk AG-UI; grounded → cockpit/selfwiki cited Q&A; tool → platform
# AG-UI). The hosted twins stay in app/api/chat.py.
mount_domains(app)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
