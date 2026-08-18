"""The on-call triage agent — LangGraph, written the way LangGraph is written.

ADR-020: each framework is used the most canonical way its own documentation shows. This
module therefore looks like a LangGraph project, not like the Agent Framework modules next to
it, and that is the point. `create_agent` + `HumanInTheLoopMiddleware` + a checkpointer is the
shape LangChain documents; anyone arriving from their docs or samples can read this.

What this domain exercises that the Agent Framework ones cannot:

  * **Four approval decisions.** `approve` · `edit` · `reject` · `respond`. The Agent
    Framework's approval is a boolean, so `edit` — the approver correcting an action before it
    runs — has no expression there (ADR-019's comparison table).
  * **A checkpointer.** LangGraph persists graph state across the interrupt and resumes with
    `Command(resume=…)`. That dependency is real and is the honest price of this runtime;
    ADR-020 records it as such.

What it does NOT get to redefine, because the guarantees are contracts rather than code paths:
the caller's role still decides who may approve (`hitl.decide`), and telemetry still goes
through `shared/telemetry`. Neither names a runtime, which is exactly why they hold here too.

The checkpointer is `InMemorySaver` for now — correct for a single process, wrong for the
`shared` deployment mode, where an interrupt must survive a request landing on another
replica. Swapping it is a checkpointer change, not a redesign, and it is called out in the
module's public docstring so nobody ships multi-tenant on top of it by accident.
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents import create_agent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.modules.hitl.public import recording_hitl
from app.modules.tickets.public import create_ticket
from app.shared.settings import settings

# Which tools stop for a human, and which decisions the approver may take. `escalate_incident`
# writes, so it stops; the read tool does not. Mirrors the platform domain's rule that reads
# flow and writes wait — expressed here in LangChain's own vocabulary rather than ours.
INTERRUPT_ON = {
    "escalate_incident": {"allowed_decisions": ["approve", "edit", "reject"]},
}

# O prompt vem do documento AgentSchema (`agents/helpdesk/oncall.yaml`), como o dos demais
# agentes. Ele vivia aqui como constante, e era a última exceção à regra 7 do CLAUDE.md — o que
# impedia publicar texto sem rebuild (ADR-014) e deixava este agente sem persona, guardrails e
# skills. O runtime segue sendo LangGraph: migrar o prompt não migra o grafo.
from app.modules.agentdefs.public import ONCALL_INSTRUCTIONS


@tool
def assess_severity(symptom: Annotated[str, "What the user reported."]) -> str:
    """Classify an incident's severity from its symptom. Read-only: never stops for approval."""
    lowered = symptom.lower()
    # Keywords in BOTH languages: the product answers in Brazilian Portuguese, and an
    # English-only keyword list silently classified "o checkout está fora do ar" as sev3 —
    # the classifier was blind to the language its own users write in.
    if any(w in lowered for w in (
        "fora do ar", "indisponível", "caiu", "perda de dados", "vazamento", "invasão",
        "down", "outage", "data loss", "breach",
    )):
        return "sev1 — indisponibilidade para o usuário ou risco a dados; escale agora"
    if any(w in lowered for w in (
        "lento", "lentidão", "degradado", "taxa de erro", "intermitente", "instável",
        "slow", "degraded", "error rate", "flaky",
    )):
        return "sev2 — degradado mas servindo; escale se persistir"
    return "sev3 — sem impacto observado ao usuário; tratar em horário comercial"


@tool
def escalate_incident(
    summary: Annotated[str, "One line describing what needs a human."],
    severity: Annotated[str, "sev1 | sev2 | sev3"],
    # O PORQUÊ é ARGUMENTO da tool, não um campo separado: no HITL do LangGraph o card mostra
    # os argumentos da chamada, então o motivo chega ao aprovador pelo caminho que já existe —
    # e, quando ele CORRIGE a escalação, corrige o motivo junto.
    reason: Annotated[str, "One sentence on what led you to escalate — read by the human approver before they approve."] = "",
) -> str:
    """Escalate an incident by opening a ticket. WRITE — always stops for human approval."""
    ticket = create_ticket(f"[{severity}] {summary}", domain="oncall")
    return f'ticket {ticket["id"]} opened: {ticket["summary"]}'


def build_oncall_graph():
    """A compiled LangGraph agent with human-in-the-loop on the write tool.

    The checkpointer is required, not optional: `HumanInTheLoopMiddleware` interrupts the graph,
    and without persisted state there is nothing to resume into.
    """
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from langchain_openai import AzureChatOpenAI

    # RULE #2 survives the runtime change, which is the point of ADR-020: LangChain's own
    # Azure client accepts an AD token provider, so no API key enters the picture. The auth
    # contract lives in `shared`; only the client that consumes it is framework-specific.
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    # O MESMO `record_usage` do resto do backend, pelo ponto canônico do LangChain. Estes dois
    # domínios não passam pela fábrica de cliente do agent-framework, então o `ChatMiddleware` que
    # mede todo o resto não os alcança — ficavam inteiramente fora da contabilidade. `callbacks` é
    # a superfície de observabilidade do próprio LangChain (ADR-020: cada framework do jeito dele),
    # e o destino é compartilhado: uma contabilidade, dois pontos de entrada.
    from app.modules.conversations.public import usage_callback

    model = AzureChatOpenAI(
        azure_deployment=settings.oncall_model,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=token_provider,
        callbacks=[usage_callback()],
    )
    return create_agent(
        model=model,
        tools=[assess_severity, escalate_incident],
        system_prompt=ONCALL_INSTRUCTIONS,
        middleware=[recording_hitl(INTERRUPT_ON, "oncall")],
        checkpointer=InMemorySaver(),
    )
