"""Per-user Foundry memory (Phase 3).

FoundryMemoryProvider is a context provider: before a run it searches the user's
memories (preferences, past resolutions) and injects them; after the run it
stores new memories. Scoping by the authenticated user's object id isolates each
developer's memory — the primary defense against memory poisoning.

API verified against agent-framework foundry: FoundryMemoryProvider(
project_endpoint, credential, memory_store_name, scope, update_delay).
"""

from agent_framework.foundry import FoundryMemoryProvider
from azure.core.credentials import TokenCredential

from app.settings import settings

MEMORY_CONTEXT_PROMPT = (
    "Known facts about this developer from past sessions (use when relevant):"
)


def memory_enabled() -> bool:
    return bool(settings.foundry_project_endpoint and settings.foundry_memory_store)


def build_memory_provider(
    credential: TokenCredential, scope: str
) -> FoundryMemoryProvider | None:
    """Memory provider scoped to one user, or None when memory isn't configured."""
    if not memory_enabled():
        return None
    return FoundryMemoryProvider(
        project_endpoint=settings.foundry_project_endpoint,
        credential=credential,
        memory_store_name=settings.foundry_memory_store,
        scope=scope,
        context_prompt=MEMORY_CONTEXT_PROMPT,
        update_delay=0,  # store immediately (default waits 5 min)
    )
