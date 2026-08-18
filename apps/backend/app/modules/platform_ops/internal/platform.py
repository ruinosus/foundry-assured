"""Platform/ops domain — a TOOL-driven agent (not KB-grounded).

Unlike the grounded experts (techdocs/selfwiki), this agent's capability is the set of
Microsoft first-party MCP tools assembled per-request from app/agents/mcp/. Tools are
role-filtered (Reader sees reads, Author/Admin see writes) and, for OBO servers, run as the
signed-in user. The /platform endpoint requires sign-in; the per-request tool build reads the
caller's roles + OBO credential from the request context (set by the auth dependency).

APIs mirror app/agents/selfwiki.py (agent-framework 1.9.0).
"""

from __future__ import annotations

from agent_framework import Agent, ToolApprovalMiddleware
from agent_framework.foundry import FoundryChatClient

from app.modules.agentdefs.public import PLATFORM_INSTRUCTIONS
from app.modules.grounded.public import PerRequestAgent
from app.modules.platform_ops.internal.mcp_tools import build_mcp_tools
from app.modules.tenancy.public import (
    tenant_config,  # per-tenant (foundry endpoint/model)
)
from app.shared.auth import credential_for_request
from app.shared.settings import settings  # platform-global (mcp_enabled)


def platform_configured() -> bool:
    if settings.deployment_mode == "shared":
        return bool(settings.mcp_enabled)  # shared: mount if MCP globally on; per-tenant gated at request time
    return bool(settings.mcp_enabled and tenant_config().foundry_project_endpoint)


# ── Human-in-the-loop ────────────────────────────────────────────────────────
# `ToolApprovalMiddleware` is the framework's own approval machinery, adopted rather than
# rebuilt (HITL spec §2). It queues concurrent approval requests, carries standing approvals
# across the same AgentSession, and is where auto-approval rules would go.
#
# `auto_approval_rules` is EMPTY on purpose (invariant H-4): nothing starts "on the loop".
# A rule here would let a tool run without asking, and that promotion is a deliberate human
# decision backed by the approval metrics — not a default.
#
# What this middleware does NOT do, and must not be expected to: check WHO is approving.
# The framework has no notion of a required role. Authorization stays where it already is —
# `build_mcp_tools()` filters by the caller's roles (min_role / min_role_write) BEFORE the
# agent ever sees a tool, so a rule can only ever be consulted for tools the caller is
# already entitled to. RULE #5 depends on that ordering.
class _RecordingToolApproval(ToolApprovalMiddleware):
    """A aprovação nativa, com a decisão REGISTRADA na trilha (ADR-023).

    Subclasse mínima em vez de middleware paralelo: a máquina de aprovação continua sendo a do
    framework (ADR-009 decidiu não reconstruí-la), e daqui só se OBSERVA. Um segundo middleware
    de aprovação seria uma segunda máquina, com o risco de as duas discordarem sobre o que foi
    aprovado — e a que registra discordar da que decide é o pior desfecho possível.

    `_prepare_inbound_messages` é onde a decisão humana entra: as mensagens chegam com conteúdos
    do tipo `function_approval_response`. Registrar antes de delegar garante que o evento existe
    mesmo que o processamento seguinte falhe.

    A gravação NÃO é fail-closed aqui, ao contrário da do `hitl.decide`. A diferença é onde o
    controle mora: ali a nossa função decide E executa, então bloquear é possível; aqui quem
    executa é o framework, e levantar no meio do `process` deixaria a sessão num estado que não
    controlamos. O evento de ESCRITA, esse sim, é gravado em `create_ticket` — e cobre o
    resultado mesmo quando a decisão escapa.
    """

    def _prepare_inbound_messages(self, messages, state):  # type: ignore[override]
        import contextlib

        for mensagem in messages:
            for conteudo in getattr(mensagem, "contents", None) or []:
                if getattr(conteudo, "type", "") != "function_approval_response":
                    continue
                with contextlib.suppress(Exception):
                    from app.modules.audit.public import actor, actor_detail, record
                    from app.shared.auth import current_roles

                    aprovado = bool(getattr(conteudo, "approved", False))
                    chamada = getattr(conteudo, "function_call", None)
                    ferramenta = getattr(chamada, "name", "") or "?"
                    record(
                        scope="approvals",
                        actor=actor(),
                        kind="approval",
                        summary=f"{'approve' if aprovado else 'reject'} em {ferramenta}",
                        ref=ferramenta,
                        # Os ARGUMENTOS da tool não entram: eles carregam o conteúdo da operação.
                        detail={"decision": "approve" if aprovado else "reject",
                                "roles": sorted(current_roles()),
                                "domain": "platform", **actor_detail()},
                    )
        return super()._prepare_inbound_messages(messages, state)


def _approval_middleware() -> ToolApprovalMiddleware:
    """The framework's approval middleware, with no auto-approval rules (H-4)."""
    return _RecordingToolApproval(source_id="tool_approval", auto_approval_rules=None)


def build_platform_agent() -> Agent:
    """A tool-driven concierge over the Microsoft first-party MCP servers."""
    cfg = tenant_config()
    client = FoundryChatClient(
        project_endpoint=cfg.foundry_project_endpoint or None,
        model=cfg.foundry_model,
        credential=credential_for_request(),
    )
    return client.as_agent(
        name="PlatformConcierge",
        description="Engineering-platform concierge over Microsoft first-party MCP tools.",
        instructions=PLATFORM_INSTRUCTIONS,
        tools=build_mcp_tools(),
        middleware=[_approval_middleware()],
    )


# The platform endpoint's serving object: the generic per-request proxy (app/agents/per_request.py)
# rebuilds `build_platform_agent()` on every `.run()`, so each request gets tools filtered by the
# CURRENT caller's roles + OBO credential. `add_agent_framework_fastapi_endpoint(agent=...)` wants a
# `SupportsAgentRun` *instance*, not a factory — the proxy IS that instance. The name/description
# overrides advertise the platform identity (the generic default would be "platform").
platform_agent_proxy = PerRequestAgent(
    "platform", build_platform_agent,
    name="PlatformConcierge",
    description="Engineering-platform concierge over Microsoft first-party MCP tools.",
)
