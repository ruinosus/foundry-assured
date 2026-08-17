"""The helpdesk workflow: triage -> retrieve -> resolve, built per request.

Phase 3 makes the workflow per-request so each run uses the *signed-in user's*
On-Behalf-Of credential (Foundry, KB, and memory called as that user) and their
own memory scope. The AG-UI workflow factory receives only a thread_id, so the
user identity comes from the request-scoped contextvar set by the auth dependency
(see app.shared.auth).

When auth is disabled, credential_for_request() falls back to
DefaultAzureCredential and memory_scope() to a dev scope, so this also works
locally without Entra.

WorkflowBuilder API verified against agent-framework 1.9.0.
"""

from agent_framework import Workflow, WorkflowBuilder

from app.modules.conversations.public import build_history_provider, conversation_user
from app.modules.helpdesk.internal.agents import (
    build_resolve_agent,
    build_retrieve_agent,
    build_triage_agent,
)
from app.modules.helpdesk.internal.escalation import EscalationExecutor
from app.modules.helpdesk.internal.memory import build_memory_provider
from app.modules.tenancy.public import memory_scope
from app.shared.auth import credential_for_request


def build_helpdesk_workflow(thread_id: str | None = None) -> Workflow:
    """Per-request factory: builds the workflow with the current user's identity."""
    credential = credential_for_request()
    scope = memory_scope()

    memory = build_memory_provider(credential, scope)
    # O histórico entra no MESMO ponto que a memória, e os dois são coisas diferentes: memória são
    # fatos extraídos que valem entre conversas; histórico é esta conversa, para o usuário poder
    # voltar a ela. Fica no `resolve` porque é o agente que fala com a pessoa — triage e retrieve
    # são passos internos, e gravá-los encheria a transcrição de ruído que ninguém vai reler.
    historico = build_history_provider(conversation_user(), "helpdesk", thread_id or "")

    providers = [p for p in (memory, historico) if p]

    triage = build_triage_agent(credential)
    retrieve = build_retrieve_agent(credential)
    resolve = build_resolve_agent(
        credential, context_providers=providers or None
    )
    escalate = EscalationExecutor()

    # triage -> retrieve -> resolve -> escalate. The escalate node turns a
    # "TICKET:" signal from resolve into a human-approval interrupt (request_info)
    # and only opens the ticket once approved. No explicit output_from: it caused
    # duplicate TOOL_CALL_START; step streaming comes from executor STEP events.
    return (
        WorkflowBuilder(
            name="HelpdeskConcierge",
            description="Triage -> retrieve -> resolve -> escalate helpdesk workflow.",
            start_executor=triage,
        )
        .add_chain([triage, retrieve, resolve, escalate])
        .build()
    )
