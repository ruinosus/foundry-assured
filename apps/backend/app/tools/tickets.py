"""A real (persisted) ticket tool — replaces the simulated ticket id.

`create_ticket` is a genuine action: it persists a ticket to data/tickets.jsonl
and returns it. It's also exposed as an agent-framework `@tool` (FunctionTool) so a
model can call it autonomously (the hosted agent does this); in the live workflow
it's gated behind human approval and invoked by the EscalationExecutor. Tickets are
viewable via the backend `GET /tickets` and the frontend `/tickets` page.

Tool API verified against agent-framework 1.9.0 (`agent_framework.tool`).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent_framework import tool

_STORE = Path(__file__).resolve().parent.parent.parent / "data" / "tickets.jsonl"


def _new_id() -> str:
    return f"HD-{uuid.uuid4().hex[:6].upper()}"


def create_ticket(summary: str, severity: str = "medium") -> dict:
    """Open a helpdesk ticket for an action the runbooks can't resolve.

    Args:
        summary: One-line description of what needs to happen.
        severity: low | medium | high.

    Returns the created ticket (id, summary, severity, status, created_at).
    """
    ticket = {
        "id": _new_id(),
        "summary": summary.strip() or "Escalation requested",
        "severity": severity if severity in ("low", "medium", "high") else "medium",
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    with _STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ticket) + "\n")
    return ticket


def list_tickets(limit: int = 50) -> list[dict]:
    """Most-recent-first list of created tickets (for the /tickets view)."""
    if not _STORE.exists():
        return []
    rows = [
        json.loads(line)
        for line in _STORE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows.reverse()
    return rows[:limit]


# The same action as a model-callable tool (used by the hosted agent).
create_ticket_tool = tool(
    create_ticket,
    name="create_ticket",
    description="Open a support ticket when the developer needs an action the runbooks "
    "can't resolve (replace hardware, reset access, escalate to a team). Returns the ticket id.",
)
