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
from datetime import UTC, datetime
from pathlib import Path

from agent_framework import tool

import app as _app

#: Ancorado no pacote `app` (RULE #9), NUNCA contado por `parents[N]` a partir deste arquivo.
#:
#: Era `Path(__file__).parent.parent.parent`, e o count estava certo quando o arquivo morava em
#: `app/tickets.py`. A ADR-017 o moveu dois níveis, e o mesmo count passou a apontar para
#: `app/modules/data/` — os chamados iam para lá havia meses, em silêncio, porque o diretório
#: simplesmente passou a existir. Foi exatamente o modo de falha que a regra 9 existe para pegar.
_STORE = Path(_app.__file__).resolve().parent / "data" / "tickets.jsonl"


def _new_id() -> str:
    return f"HD-{uuid.uuid4().hex[:6].upper()}"


def create_ticket(summary: str, severity: str = "medium", *, domain: str = "") -> dict:
    """Open a helpdesk ticket for an action the runbooks can't resolve.

    Args:
        summary: One-line description of what needs to happen.
        severity: low | medium | high.
        domain: which assistant opened it (helpdesk, oncall, …). Keyword-only DE PROPÓSITO:
            é atribuição, não conteúdo, e o modelo não deve poder escolhê-la — quem sabe o
            domínio é o código que chama, não quem escreve o texto do chamado.

    Returns the created ticket (id, summary, severity, status, created_at, domain).
    """
    ticket = {
        "id": _new_id(),
        "summary": summary.strip() or "Escalation requested",
        "severity": severity if severity in ("low", "medium", "high") else "medium",
        "status": "open",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # Sem isto, o painel de ROI contava TODOS os chamados para TODOS os casos: três
        # chamados de plantão zeravam o resultado do helpdesk. Atribuir por heurística (adivinhar
        # pelo texto) daria um número que parece preciso e não é.
        "domain": domain,
    }
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    with _STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ticket) + "\n")
    return ticket


def list_tickets(limit: int = 50, domain: str = "") -> list[dict]:
    """Most-recent-first list of created tickets (for the /tickets view).

    Com `domain`, devolve só os daquele assistente. Chamado ANTIGO, gravado antes deste campo
    existir, fica de fora de uma consulta filtrada — e isso é deliberado: não sabemos de qual
    caso ele veio, e incluí-lo em todos inflaria a escalação de cada um deles.
    """
    if not _STORE.exists():
        return []
    rows = [
        json.loads(line)
        for line in _STORE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if domain:
        rows = [r for r in rows if r.get("domain") == domain]
    rows.reverse()
    return rows[:limit]


# The same action as a model-callable tool (used by the hosted agent).
create_ticket_tool = tool(
    create_ticket,
    name="create_ticket",
    description="Open a support ticket when the developer needs an action the runbooks "
    "can't resolve (replace hardware, reset access, escalate to a team). Returns the ticket id.",
)
