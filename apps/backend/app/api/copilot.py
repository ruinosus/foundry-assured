"""Tech Copilot router — detect technical questions in a call + answer them from the
cockpit + selfwiki KBs.

Retrieval + synthesis REUSE the shipped grounded pieces (app.services.copilot →
app.services.retrieval + app.services.grounded); only detection is new. Called by the Coach
Overlay's MAIN process over plain HTTP (no browser origin → no CORS).

Auth: in dev (settings.auth_enabled false) the routes run open and answer as the
DefaultAzureCredential identity. To enable per-user ACL, add `dependencies=auth_dependencies()`
to the router (Mode B in the design doc) so `current_user()` is populated → OBO downstream.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.detector import detect_question
from app.core.auth import current_user
from app.services.copilot import answer_question

router = APIRouter(prefix="/copilot", tags=["copilot"])


class DetectBody(BaseModel):
    transcript_window: list[dict]


class AskBody(BaseModel):
    query: str
    meeting_type: str = "presentation"


@router.get("/ping")
async def ping() -> dict:
    """Health check for the Coach Overlay Tech Copilot."""
    return {"status": "ok", "kbs": ["cockpit", "selfwiki"], "version": "0.1.0"}


@router.post("/detect")
async def detect(body: DetectBody) -> dict:
    """Stateless question detection over a transcript window (the window lives in the overlay)."""
    return detect_question(body.transcript_window)


@router.post("/ask")
async def ask(body: AskBody) -> dict:
    """Answer a technical question from cockpit + selfwiki with cited sources."""
    result = await answer_question(
        body.query, user=current_user(), meeting_type=body.meeting_type
    )
    return {"question": body.query, **result}
