"""Agentic retrieval with a direct-semantic fallback.

The Foundry IQ **agentic** retrieve intermittently returns an EMPTY chunk array even when
the index plainly holds relevant content — observed on broad/operational queries (e.g.
"what's the cost to run this project"). An empty context makes the agent decline blind, as
if the KB knew nothing, when a plain semantic search on the same index returns good hits.

So whenever the agentic pass comes back empty we fall back to a direct semantic search on
the underlying index and surface those chunks as context. Agentic completeness is kept
when it works; semantic reliability backs it up when it doesn't — the agent grounds
whenever the content exists.
"""

from __future__ import annotations

import json

from agent_framework import Message
from agent_framework.azure import AzureAISearchContextProvider
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

from app.core.tenant import tenant_config

_API = "2026-05-01-preview"


def _last_user_text(messages: list[Message]) -> str | None:
    for m in reversed(messages or []):
        if getattr(m, "role", None) != "user":
            continue
        for c in m.contents or []:
            t = getattr(c, "text", None) or (c if isinstance(c, str) else None)
            if t:
                return t
    return None


def _has_chunks(result: list[Message]) -> bool:
    """True if the agentic result carries any non-empty context."""
    for m in result or []:
        for c in m.contents or []:
            t = getattr(c, "text", None)
            if not t:
                continue
            try:
                arr = json.loads(t)
                if isinstance(arr, list):
                    if arr:
                        return True
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            if t.strip():
                return True
    return False


class GroundedAzureAISearchProvider(AzureAISearchContextProvider):
    """Agentic provider that falls back to direct semantic search when agentic is empty.

    fallback_index: the search index behind the knowledge base (the agentic KB wraps it),
    queried directly when the agentic pass returns nothing.
    """

    def __init__(self, *args, fallback_index: str, fallback_top: int = 8, **kwargs):  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self._fallback_index = fallback_index
        self._fallback_top = fallback_top

    def _direct_semantic(self, query: str) -> list[dict]:
        sc = SearchClient(
            endpoint=tenant_config().azure_search_endpoint,
            index_name=self._fallback_index,
            credential=DefaultAzureCredential(),
            api_version=_API,
        )
        out: list[dict] = []
        for i, h in enumerate(sc.search(search_text=query, top=self._fallback_top, select=["snippet", "blob_url"])):
            snippet = h.get("snippet") or ""
            if not snippet:
                continue
            blob = str(h.get("blob_url", "")).rsplit("/", 1)[-1]
            # Keep the chunk citable: if it doesn't already carry an H1 label, prefix its source.
            content = snippet if snippet.lstrip().startswith("#") else f"(fonte: {blob})\n{snippet}"
            out.append({"ref_id": blob or str(i), "content": content})
        return out

    async def _agentic_search(self, messages: list[Message]) -> list[Message]:  # type: ignore[override]
        result = await super()._agentic_search(messages)
        if _has_chunks(result):
            return result
        query = _last_user_text(messages)
        if not query:
            return result
        try:
            chunks = self._direct_semantic(query)
        except Exception:  # noqa: BLE001 — fallback must never crash the turn
            return result
        if not chunks:
            return result
        role = result[0].role if result else "user"
        return [Message(role=role, contents=[json.dumps(chunks, ensure_ascii=False)])]
