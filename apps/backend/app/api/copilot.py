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

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.detector import detect_question
from app.core.auth import auth_dependencies, current_user
from app.services.copilot import (
    answer_direct,
    answer_question,
    extract_nodes,
    extract_nodes_stream,
    kb_fetch,
    propose_edges,
    refine_question,
)

router = APIRouter(prefix="/copilot", tags=["copilot"])

# Mirror the grounded endpoints: when auth is ON, /detect and /ask require a validated
# bearer token (→ current_user() populated → OBO → per-user ACL, Mode B). When auth is OFF
# (local dev, Mode A) auth_dependencies() is empty, so they run open as DefaultAzureCredential.
# /ping stays open in both modes (pure health check, no Azure calls).
_auth = auth_dependencies()


class DetectBody(BaseModel):
    transcript_window: list[dict]


class AskBody(BaseModel):
    query: str
    meeting_type: str = "presentation"


class RefineBody(BaseModel):
    text: str


class AnswerDirectBody(BaseModel):
    text: str
    prompt: str = "responder"


class ExtractBody(BaseModel):
    transcript_window: list[dict]
    existing_nodes: list[dict] = []


class EdgesBody(BaseModel):
    nodes: list[dict]


@router.get("/ping")
async def ping() -> dict:
    """Health check for the Coach Overlay Tech Copilot."""
    return {"status": "ok", "kbs": ["cockpit", "selfwiki"], "version": "0.1.0"}


@router.post("/detect", dependencies=_auth)
async def detect(body: DetectBody) -> dict:
    """Stateless question detection over a transcript window (the window lives in the overlay)."""
    return detect_question(body.transcript_window)


@router.post("/ask", dependencies=_auth)
async def ask(body: AskBody) -> dict:
    """Answer a technical question from cockpit + selfwiki with cited sources."""
    result = await answer_question(
        body.query, user=current_user(), meeting_type=body.meeting_type
    )
    return {"question": body.query, **result}


@router.post("/refine", dependencies=_auth)
async def refine(body: RefineBody) -> dict:
    """Consolidate a messy transcript slice into one clean question (optional pre-ask agent)."""
    return {"question": await refine_question(body.text, user=current_user())}


@router.post("/answer-direct", dependencies=_auth)
async def answer_direct_route(body: AnswerDirectBody) -> dict:
    """Sabatina: LLM-direct answer from selected transcript lines (no KB, no sources)."""
    return await answer_direct(body.text, body.prompt, user=current_user())


@router.post("/extract", dependencies=_auth)
async def extract(body: ExtractBody) -> dict:
    """Propose conversation nodes (+ raw edges) from a transcript window (Meeting Board)."""
    return await extract_nodes(body.transcript_window, body.existing_nodes, user=current_user())


@router.post("/extract-stream", dependencies=_auth)
async def extract_stream(body: ExtractBody) -> StreamingResponse:
    """Stream proposed nodes one-per-SSE-event as the model generates them (Meeting Board)."""
    user = current_user()  # capture in the endpoint (contextvar is lost inside the generator)

    async def gen():
        try:
            async for node in extract_nodes_stream(body.transcript_window, body.existing_nodes, user):
                yield f"data: {json.dumps(node, ensure_ascii=False)}\n\n"
        except Exception:  # noqa: BLE001 — fail-soft
            pass
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/edges", dependencies=_auth)
async def edges(body: EdgesBody) -> dict:
    """Propose edges (by id) among existing Board nodes (Meeting Board P2)."""
    return await propose_edges(body.nodes, user=current_user())


class KbFetchBody(BaseModel):
    query: str


@router.post("/kb-fetch", dependencies=_auth)
async def kb_fetch_route(body: KbFetchBody) -> dict:
    """Fetch full KB doc content for a Board node (markdown/mermaid + enrichment source)."""
    return await kb_fetch(body.query, user=current_user())
