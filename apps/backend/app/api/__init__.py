"""Aggregates the HTTP routers. The AG-UI workflow endpoint (`/helpdesk`) is
registered separately on the app in app/main.py."""

from fastapi import APIRouter

from app.api import health
from app.modules.admin import api_admin, api_me
from app.modules.evaluation import api as evals
from app.modules.hosted import api as chat
from app.modules.tickets import api as tickets
from app.shared.settings import settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tickets.router)
api_router.include_router(evals.router)
api_router.include_router(chat.router)
api_router.include_router(api_admin.router)
api_router.include_router(api_me.router)

if settings.deployment_mode == "shared":
    from app.api import tenant
    api_router.include_router(tenant.router)
