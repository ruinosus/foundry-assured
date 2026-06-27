"""Phase 4 — security-trimmed agentic retrieval (Path A, service-side).

Subclasses AzureAISearchContextProvider so the agentic retrieve carries the *caller's*
Entra identity as `x-ms-query-source-authorization`. Azure AI Search then trims results
to the documents the signed-in user is entitled to — matching the per-document
`groupIds` stamped at ingest. The service credential still authenticates to the search
service; the user token only represents *whose* content access is evaluated, and is
omitted (no trimming) when auth is off, e.g. local dev.

Verified against the installed agent_framework_azure_ai_search: `_agentic_search` calls
`self._retrieval_client.retrieve(...)`, and `KnowledgeBaseRetrievalClient.retrieve`
accepts `x_ms_query_source_authorization`. Rather than duplicate the (version-specific)
request-building, we wrap the client's `retrieve` to inject the per-request user token,
read from the OBO contextvar at call time — so a single shared agent stays
request-correct (contextvars are per-async-task).
"""

from __future__ import annotations

from agent_framework.azure import AzureAISearchContextProvider

from app.core.auth import credential_for_request, current_user
from app.core.settings import settings

_SEARCH_SCOPE = "https://search.azure.com/.default"


def _caller_search_token() -> str | None:
    """The signed-in user's search-scoped token (OBO), or None when auth is off."""
    if not (settings.auth_enabled and current_user() is not None):
        return None
    try:
        return credential_for_request().get_token(_SEARCH_SCOPE).token
    except Exception:  # noqa: BLE001 — fall back to no trimming rather than failing the turn
        return None


class SecureAzureAISearchProvider(AzureAISearchContextProvider):
    """Agentic provider that passes the caller identity for query-time ACL trimming."""

    async def _ensure_knowledge_base(self) -> None:  # type: ignore[override]
        await super()._ensure_knowledge_base()
        client = self._retrieval_client
        if client is not None and not getattr(client, "_obo_wrapped", False):
            original_retrieve = client.retrieve

            async def retrieve_as_caller(*args, **kwargs):  # noqa: ANN002, ANN003
                token = _caller_search_token()
                if token and not kwargs.get("x_ms_query_source_authorization"):
                    kwargs["x_ms_query_source_authorization"] = token
                return await original_retrieve(*args, **kwargs)

            client.retrieve = retrieve_as_caller  # type: ignore[method-assign]
            client._obo_wrapped = True  # type: ignore[attr-defined]
