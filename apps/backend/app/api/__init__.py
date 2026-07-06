"""Aggregates the HTTP routers. The AG-UI workflow endpoint (`/helpdesk`) is
registered separately on the app in app/main.py."""

from fastapi import APIRouter

from app.api import admin, chat, copilot, evals, health, me, tickets
from app.core.settings import settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tickets.router)
api_router.include_router(evals.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)
api_router.include_router(me.router)
api_router.include_router(copilot.router)

if settings.deployment_mode == "shared":
    from app.api import tenant
    api_router.include_router(tenant.router)
