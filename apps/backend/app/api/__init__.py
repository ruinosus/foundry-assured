"""Aggregates the HTTP routers. The AG-UI workflow endpoint (`/helpdesk`) is
registered separately on the app in app/main.py."""

from fastapi import APIRouter

from app.api import chat, evals, health, tickets

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(tickets.router)
api_router.include_router(evals.router)
api_router.include_router(chat.router)
