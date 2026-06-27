"""Cockpit expert agent — a second domain alongside the helpdesk.

Same Foundry IQ pattern as the concierge, pointed at the **cockpit-kb** (the Cockpit
platform docs ingested by app/knowledge/ingest_cockpit.py). Pure grounded Q&A — no
workflow steps or ticket escalation; the Cockpit corpus is reference knowledge.

The Cockpit KB is org-wide (not per-user), so this runs under the app's own identity
(DefaultAzureCredential), not OBO. The /cockpit endpoint still requires sign-in.
"""

from pathlib import Path

from agent_framework import Agent, FileSkillsSource, SkillsProvider, agent_middleware
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.agents.prompts import COCKPIT_INSTRUCTIONS
from app.core.settings import settings

# Agent Skills (open SKILL.md standard) — the grounded-qa skill carries the answering
# discipline (cite sources, decline off-corpus, prefer authoritative architecture docs).
# It is pure procedure: it has NO reference resources to fetch — the KB documents are
# injected into context by the AzureAISearchContextProvider (agentic retrieval), so the
# model answers from that context and must not call read_skill_resource for domain docs.
_SKILLS_DIR = Path(__file__).parent / "skills"


def _is_tool_content(content) -> bool:
    # Match ONLY function-call / function-result content, by its `.type` discriminator
    # (the same field the AG-UI adapter keys on). Plain text content is `type="text"`
    # with `call_id=None` — must NOT match, or we'd strip the user's own message and
    # starve retrieval. (An earlier `hasattr(content, "call_id")` check did exactly that,
    # since text content carries `call_id=None`, killing the agentic retrieval.)
    return getattr(content, "type", None) in (
        "function_call",
        "function_result",
        "tool_call",
        "tool_result",
    )


@agent_middleware
async def _drop_replayed_tool_messages(context, call_next):
    """Make the grounded-qa skill safe across turns over AG-UI.

    The SkillsProvider has the model emit `load_skill` / `read_skill_resource` *tool
    calls* to consult the skill. The AG-UI thread replays those prior calls on the next
    message *without* their paired tool outputs (CopilotKit doesn't round-trip tool
    results), so the Responses API rejects the continuation: "No tool output found for
    function call …". We strip tool-call / result messages from the incoming history —
    they're internal bookkeeping, not needed for follow-up context — so only
    user/assistant text remains. The fresh turn re-loads the skill as needed; its
    call+output are paired within this turn, so nothing breaks.

    (Note: the *agentic retrieval* itself does NOT emit a model tool call — it runs in
    a context-provider hook (`before_run`), so it isn't the source of the orphan. Only
    the skill tool calls are. Keeping the filter precise — matching `.type`, never the
    user's plain-text message — is essential, or retrieval gets starved of the query.)
    """
    msgs = context.messages
    if msgs:
        msgs[:] = [
            m for m in msgs
            if not any(_is_tool_content(c) for c in (getattr(m, "contents", None) or []))
        ]
    await call_next()


def cockpit_configured() -> bool:
    return bool(settings.azure_search_endpoint and settings.cockpit_search_knowledge_base)


def build_cockpit_agent() -> Agent:
    """A grounded expert over the Cockpit knowledge base, using the grounded-qa skill."""
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint or None,
        model=settings.foundry_model,
        credential=credential,
    )
    # Agentic retrieval (Foundry IQ KB query planning) — best quality on broad questions.
    # Runs in a context-provider hook (before_run), injecting the retrieved Cockpit docs
    # into context; it does NOT emit a model tool call. The grounded-qa skill below DOES
    # emit tool calls, which is why _drop_replayed_tool_messages is needed for multi-turn.
    search = AzureAISearchContextProvider(
        endpoint=settings.azure_search_endpoint,
        knowledge_base_name=settings.cockpit_search_knowledge_base,
        credential=credential,
        mode="agentic",
    )
    skills = SkillsProvider(FileSkillsSource([str(_SKILLS_DIR)]))
    return client.as_agent(
        name="CockpitExpert",
        description="Avanade Cockpit platform expert grounded in the Cockpit knowledge base.",
        instructions=COCKPIT_INSTRUCTIONS,
        context_providers=[search, skills],
        middleware=[_drop_replayed_tool_messages],
    )
