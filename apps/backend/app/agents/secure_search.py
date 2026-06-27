"""Phase 4 — security-trimmed agentic retrieval (defense-in-depth).

Two layers protect the agent:

  • **C (service-side, the hook):** the agentic retrieve carries the caller's identity
    (`x-ms-query-source-authorization`). On a search service that enforces ACLs in the
    *agentic* path, this trims server-side — inert today on our service version, but it
    activates automatically when the service supports it.

  • **B (app-side, active now):** our service does NOT trim the *agentic* retrieve per
    user (it returns content to any valid token), so we trim in the app. After the
    agentic retrieve (full recall), we ask the index the same query **as the caller** via
    a direct search — which DOES trim correctly — to learn the **set of components the
    caller is entitled to**, then drop any agentic chunk from a component outside that
    set, **before the model sees it**. Authoritative (the trim comes from the search
    service's own ACL evaluation, not a guess) and fail-closed (unmatched chunks dropped).

With auth off (local dev) there's no caller, so nothing is trimmed.
"""

from __future__ import annotations

import json
import re
import urllib.request

from agent_framework import Message
from agent_framework.azure import AzureAISearchContextProvider
from azure.identity import DefaultAzureCredential

from app.core.auth import credential_for_request, current_user
from app.core.settings import settings
from app.knowledge.acl_setup import _canonical, _component

_SEARCH_SCOPE = "https://search.azure.com/.default"
_INDEX = settings.cockpit_search_index
_API = "2025-08-01-preview"


def _caller_search_token() -> str | None:
    """The signed-in user's search-scoped token (OBO), or None when auth is off."""
    if not (settings.auth_enabled and current_user() is not None):
        return None
    try:
        return credential_for_request().get_token(_SEARCH_SCOPE).token
    except Exception:  # noqa: BLE001 — no token → fail-closed below
        return None


def authorized_components(caller_token: str) -> set[str]:
    """The components the caller may read — the caller's *entitlement* (query-independent),
    from a direct search (`*`) that the search service trims by the caller's identity.
    Pages through @odata.nextLink so a broadly-entitled caller on a large corpus isn't
    capped at the first page (which would silently over-trim, never leak)."""
    service = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token
    headers = {"Authorization": f"Bearer {service}", "x-ms-query-source-authorization": caller_token}
    url: str | None = (f"{settings.azure_search_endpoint}/indexes/{_INDEX}/docs"
                       f"?api-version={_API}&search=*&$top=1000&$select=blob_url")
    components: set[str] = set()
    try:
        while url:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as r:
                page = json.load(r)
            components |= {_component(d.get("blob_url", "")) for d in page.get("value", []) if d.get("blob_url")}
            url = page.get("@odata.nextLink")
    except Exception:  # noqa: BLE001 — on error, fail-closed (drop all rather than leak)
        return set()
    return components


def _chunk_component(content: str) -> str:
    """The component key a chunk belongs to, from its H1 — handling both ingest formats:
    component pages (`# cockpit-mcp-agent v1.2.0 — …` → `cockpit-mcp-agent`) and source
    pages (`# Cockpit (fonte): Architecture` → `source__ARCHITECTURE`). Deterministic
    identity extraction (matches the ingest's labeling), not classification."""
    first = (content or "").lstrip().split("\n", 1)[0]
    label = (first[2:] if first.startswith("# ") else first).strip()
    if label.lower().startswith("cockpit (fonte):"):
        title = label.split(":", 1)[1].strip()
        return "source__" + re.sub(r"\s+", "_", title).upper()
    head = re.split(r"\s+[—–]\s+", label, 1)[0]
    return _canonical(head)  # same normalization as acl_setup._component → keys match


def _chunk_authorized(content: str, allowed: set[str]) -> bool:
    """Keep a chunk only if its source component is in the caller's authorized set.
    Unmatched / unattributable → dropped (fail-closed)."""
    return _chunk_component(content) in allowed


def trim_agentic_content(text: str, allowed: set[str]) -> str:
    """Filter the agentic chunk array to the caller's authorized components."""
    try:
        chunks = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    if not isinstance(chunks, list):
        return text
    kept = [c for c in chunks if _chunk_authorized(
        (c.get("content", "") if isinstance(c, dict) else str(c)), allowed)]
    return json.dumps(kept, ensure_ascii=False)


class SecureAzureAISearchProvider(AzureAISearchContextProvider):
    """Agentic provider with caller-identity passthrough (C) + app-side trim (B)."""

    async def _ensure_knowledge_base(self) -> None:  # type: ignore[override]
        await super()._ensure_knowledge_base()
        client = self._retrieval_client
        if client is not None and not getattr(client, "_obo_wrapped", False):
            original_retrieve = client.retrieve

            async def retrieve_as_caller(*args, **kwargs):  # noqa: ANN002, ANN003
                token = _caller_search_token()
                if token and not kwargs.get("x_ms_query_source_authorization"):
                    kwargs["x_ms_query_source_authorization"] = token  # layer C
                return await original_retrieve(*args, **kwargs)

            client.retrieve = retrieve_as_caller  # type: ignore[method-assign]
            client._obo_wrapped = True  # type: ignore[attr-defined]

    async def _agentic_search(self, messages: list[Message]) -> list[Message]:  # type: ignore[override]
        result = await super()._agentic_search(messages)
        token = _caller_search_token()
        if token is None:  # auth off (dev) → no caller to trim for
            return result
        allowed = authorized_components(token)  # layer B — the caller's entitlement
        trimmed: list[Message] = []
        for m in result:
            new_contents = [
                (trim_agentic_content(t, allowed) if (t := getattr(c, "text", None)) else c)
                for c in (m.contents or [])
            ]
            trimmed.append(Message(role=m.role, contents=new_contents))
        return trimmed
