"""Infra-free: the ONE grounded archetype (`stream_grounded`) emits the right AG-UI events.

No Azure, no credential, no network: we monkeypatch the two seams the archetype leans on —

  - `app.services.retrieval.retrieve`  → 3 fixture docs (one snippet >800 chars);
  - the Responses stream (`client.responses.create`) → yields 2 text deltas.

Then we drive `stream_grounded(body, domain, user=None)`, collect the encoded AG-UI SSE events, and lock:

  - both text deltas pass through as TEXT_MESSAGE_CONTENT;
  - a `sources` CUSTOM event fires with {index, source, url, content} per doc;
  - `content` is truncated to EXACTLY 800 chars (the cap is preserved);
  - RUN_STARTED / RUN_FINISHED bracket the run (no RUN_ERROR).

    cd apps/backend && uv run python -m eval.archetype_emit_test
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

_DOCS = [
    {"index": 1, "source": "a.md", "url": "https://x/a.md", "snippet": "X" * 1500},  # >800 → must cap
    {"index": 2, "source": "b.md", "url": "https://x/b.md", "snippet": "short B"},
    {"index": 3, "source": "c.md", "url": "https://x/c.md", "snippet": ""},
]


class _FakeEvent:
    def __init__(self, delta: str) -> None:
        self.type = "response.output_text.delta"
        self.delta = delta


class _FakeStream:
    """Async-iterable Responses stream yielding 2 text deltas."""

    def __aiter__(self):
        async def _gen():
            for d in ("Olá ", "mundo"):
                yield _FakeEvent(d)

        return _gen()


class _FakeResponses:
    async def create(self, **kwargs):
        return _FakeStream()


class _FakeOpenAIClient:
    responses = _FakeResponses()


class _FakeProjectClient:
    """Stands in for azure.ai.projects.aio.AIProjectClient — no network, no credential used."""

    def __init__(self, *a, **k) -> None:
        pass

    def get_openai_client(self):
        return _FakeOpenAIClient()

    async def close(self):
        return None


class _FakeCred:
    async def get_token(self, *a, **k):
        return SimpleNamespace(token="FAKE")

    async def close(self):
        return None


async def _fake_retrieve(query, user, domain, *, top: int = 8):
    return list(_DOCS)


def _decode(events: list[str]) -> list[dict]:
    """Encoded AG-UI SSE lines → list of parsed event dicts."""
    out: list[dict] = []
    for chunk in events:
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    out.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
    return out


async def _run() -> int:
    from app.services import grounded, retrieval

    # Patch the retrieval seam (imported inside stream_grounded from app.services.retrieval).
    retrieval.retrieve = _fake_retrieve  # type: ignore[assignment]
    # Patch the Foundry client + credential so no infra is touched.
    import azure.ai.projects.aio as _aio_proj
    import azure.identity.aio as _aio_id

    _orig_proj = _aio_proj.AIProjectClient
    _orig_cred = _aio_id.DefaultAzureCredential
    _aio_proj.AIProjectClient = _FakeProjectClient  # type: ignore[assignment,misc]
    _aio_id.DefaultAzureCredential = _FakeCred  # type: ignore[assignment,misc]

    domain = SimpleNamespace(instructions="You are helpful.", kb_name="stub-kb",
                             search_endpoint="https://stub", search_index=None)
    body = {"messages": [{"role": "user", "content": "oi"}]}

    try:
        chunks = [ev async for ev in grounded.stream_grounded(body, domain, user=None)]
    finally:
        _aio_proj.AIProjectClient = _orig_proj  # type: ignore[assignment,misc]
        _aio_id.DefaultAzureCredential = _orig_cred  # type: ignore[assignment,misc]

    events = _decode(chunks)
    types = [e.get("type") for e in events]

    # Bracketed run, no error.
    assert types[0] == "RUN_STARTED", types
    assert "RUN_FINISHED" in types, types
    assert "RUN_ERROR" not in types, [e for e in events if e.get("type") == "RUN_ERROR"]

    # Both deltas passed through, in order.
    deltas = [e.get("delta") for e in events if e.get("type") == "TEXT_MESSAGE_CONTENT"]
    assert deltas == ["Olá ", "mundo"], deltas

    # The sources CUSTOM event.
    customs = [e for e in events if e.get("type") == "CUSTOM" and e.get("name") == "sources"]
    assert len(customs) == 1, customs
    srcs = customs[0]["value"]
    assert len(srcs) == 3, srcs
    for s in srcs:
        assert set(s.keys()) == {"index", "source", "url", "content"}, s
    assert [s["index"] for s in srcs] == [1, 2, 3], srcs
    assert srcs[0]["source"] == "a.md" and srcs[0]["url"] == "https://x/a.md", srcs[0]
    # The 800-char cap is preserved (the 1500-char snippet is truncated to exactly 800).
    assert len(srcs[0]["content"]) == 800, len(srcs[0]["content"])
    assert srcs[1]["content"] == "short B", srcs[1]
    assert srcs[2]["content"] == "", srcs[2]  # empty snippet stays empty

    print("✅ PASS: stream_grounded emits deltas + sources CUSTOM event; content capped at 800 chars.")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
