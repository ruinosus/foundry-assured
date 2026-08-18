"""The three workflow agents: triage -> retrieve -> resolve.

Each agent is a Foundry-backed ChatAgent. Their `name` becomes the workflow
executor id, which the AG-UI adapter emits as the step name the frontend renders
(verified: resolve_agent_id falls back to agent.name). So names are lowercase,
UI-facing: "triage", "retrieve", "resolve".

The chain passes each agent's output to the next, so instructions are written so
every step's output is self-contained for the step that follows.
"""

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential

from app.modules.agentdefs.public import (
    RESOLVE_INSTRUCTIONS,
    RETRIEVE_INSTRUCTIONS,
    TRIAGE_INSTRUCTIONS,
)
from app.modules.tenancy.public import tenant_config


def _client(credential: TokenCredential) -> FoundryChatClient:
    # Fábrica única (foundry.public.chat_client): é ela que anexa o gravador de uso, para medir ser
    # propriedade de falar com o modelo e não de cada agente lembrar.
    from app.modules.foundry.public import chat_client

    return chat_client(credential)


def build_triage_agent(credential: TokenCredential) -> Agent:
    return _client(credential).as_agent(
        name="triage",
        description="Classifies intent and urgency, restates the question.",
        instructions=TRIAGE_INSTRUCTIONS,
    )


def build_retrieve_agent(credential: TokenCredential, provider=None) -> Agent:
    """O passo de recuperação. `provider` é o nosso `GroundedRetrieval` quando há usuário.

    POR QUE NÃO O `AzureAISearchContextProvider` DIRETO. Ele cobre grounding e citação e NÃO envia
    `x-ms-query-source-authorization` — o header de ACL por usuário (medido: zero ocorrências no
    módulo). Com ele, o helpdesk era o único domínio grounded que NÃO trimava por documento,
    enquanto techdocs e selfwiki trimavam. E a contagem de referências morria aqui, que é o insumo
    principal da fórmula de retorno.

    O nosso provider resolve os dois — é `retrieve()` (com ACL) entrando pelo `ContextProvider` do
    framework. O do framework fica como RESERVA para quando não há usuário na requisição: sem
    identidade não há ACL a aplicar, e recusar recuperar ali quebraria o dev local sem auth.
    """
    cfg = tenant_config()
    search = provider or AzureAISearchContextProvider(
        endpoint=cfg.azure_search_endpoint,
        knowledge_base_name=cfg.azure_search_knowledge_base,
        credential=credential,
        mode="agentic",
    )
    return _client(credential).as_agent(
        name="retrieve",
        description="Retrieves grounding passages + sources from the knowledge base.",
        instructions=RETRIEVE_INSTRUCTIONS,
        context_providers=[search],
    )


def build_resolve_agent(
    credential: TokenCredential, context_providers: list | None = None
) -> Agent:
    # The memory provider (when present) is attached here so it reads the dev's
    # preferences/past resolutions before resolving and stores the resolution after.
    # Ticket escalation is decided here (the "TICKET:" signal) but approval + creation
    # happen in the EscalationExecutor (HITL), so a ticket can't be opened unapproved.
    return _client(credential).as_agent(
        name="resolve",
        description="Writes the final grounded, cited answer; flags ticket escalations.",
        instructions=RESOLVE_INSTRUCTIONS,
        context_providers=context_providers or None,
    )
