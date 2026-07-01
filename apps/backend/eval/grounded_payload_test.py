"""Infra-free: grounded.py builds the correct payloads for both paths, without touching Azure.

- acl=False (selfwiki) → build_responses_kwargs: inline MCP tool + authorization.
- acl=True  (cockpit)  → build_synthesis_kwargs: direct-search docs as the ONLY grounding context.

    cd apps/backend && uv run python -m eval.grounded_payload_test
"""

from __future__ import annotations

import sys

from app.services.grounded import (
    CITATION_DIRECTIVE,
    SYNTHESIS_DIRECTIVE,
    GroundedDomain,
    build_responses_kwargs,
    build_synthesis_kwargs,
)

_EP = "https://srch.search.windows.net"


def main() -> None:
    # acl=False (selfwiki) — inline MCP tool, native citations.
    sw = GroundedDomain(kb_name="selfwiki-kb", instructions="Y", acl=False, search_endpoint=_EP)
    kw = build_responses_kwargs("q", sw, model="gpt-5-mini", search_token="STOK")
    assert kw["model"] == "gpt-5-mini" and kw["stream"] is True
    tool = kw["tools"][0]
    assert tool["type"] == "mcp" and tool["allowed_tools"] == ["knowledge_base_retrieve"], tool
    assert tool["authorization"] == "STOK", tool
    assert tool["server_url"].endswith("/knowledgebases/selfwiki-kb/mcp?api-version=2026-05-01-preview")
    assert CITATION_DIRECTIVE in kw["instructions"]

    # acl=True (cockpit) — direct-search synthesis: docs are the ONLY context, no MCP tool.
    ck = GroundedDomain(
        kb_name="cockpit-kb", instructions="X", acl=True, search_endpoint=_EP, search_index="cockpit-idx"
    )
    docs = [
        {"index": 1, "source": "a.md", "url": f"{_EP}/a.md", "snippet": "conteudo A"},
        {"index": 2, "source": "b.md", "url": f"{_EP}/b.md", "snippet": "conteudo B"},
    ]
    sk = build_synthesis_kwargs("qual a resposta?", ck, docs, model="m")
    assert "tools" not in sk, sk  # no MCP tool on the ACL path (agentic retrieve doesn't trim)
    assert sk["stream"] is True
    assert SYNTHESIS_DIRECTIVE in sk["input"]
    assert "[1] a.md" in sk["input"] and "conteudo A" in sk["input"]  # docs are the grounding context
    assert "qual a resposta?" in sk["input"]
    # empty authorized set → still asks, but with no docs (fail-closed to "não sei")
    empty = build_synthesis_kwargs("q", ck, [], model="m")
    assert "Nenhum documento autorizado" in empty["input"]

    print("PASS: grounded payloads (acl=False MCP tool; acl=True direct-search synthesis)")
    sys.exit(0)


if __name__ == "__main__":
    main()
