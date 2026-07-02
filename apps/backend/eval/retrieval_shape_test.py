"""Infra-free CONTRACT test for the single retrieval seam `retrieve()`.

Asserts the OUTPUT SHAPE without touching Azure: the low-level native fetch
(`retrieval._native_retrieve`) is monkeypatched to return fixture rows, so no
credential is acquired and no network is hit. What we lock in:

  - output is exactly [{index, source, url, snippet}]
  - `index` is 1-based
  - rows are DEDUPED by url (first-wins), then RE-INDEXED
  - `snippet` is carried through

Run (from apps/backend/):
    uv run python -m eval.retrieval_shape_test

Skips cleanly only if it needed infra — this one doesn't, so it always runs.
"""

from __future__ import annotations

import asyncio
import sys


class _StubDomain:
    """Duck-typed stand-in for the (not-yet-existing) DomainSpec. `kb_name` selects the NATIVE path
    (the only branch this test exercises — the fetch is patched, so search_endpoint/search_index are
    never read here; the fallback direct-search shape is covered elsewhere)."""

    kb_name = "stub-kb"
    search_endpoint = "https://stub.search.windows.net"
    search_index = "stub-index"


def _stub_domain() -> _StubDomain:
    return _StubDomain()


async def _aret(rows: list[dict]) -> list[dict]:
    """Async identity — the stub `_native_retrieve` returns these rows straight through."""
    return rows


async def _run() -> int:
    from app.services import retrieval

    rows = [
        {"index": 1, "source": "a.md", "url": "https://x/a.md", "snippet": "S1"},
        {"index": 2, "source": "a.md", "url": "https://x/a.md", "snippet": "dup"},
        {"index": 3, "source": "b.md", "url": "https://x/b.md", "snippet": "S2"},
    ]

    called = {"cred": False}

    # Patch the low-level native fetch: no infra, no credential should be needed for the parse/project
    # contract. (retrieve() DOES open an app credential to get the primary token before calling
    # _native_retrieve; we monkeypatch DefaultAzureCredential so that acquisition is also infra-free and
    # observable — the contract we assert is dedup + reindex, and that NO real token network call happens.)
    retrieval._native_retrieve = lambda *a, **k: _aret(rows)  # type: ignore[assignment]

    class _FakeToken:
        token = "FAKE"

    class _FakeCred:
        def __init__(self, *a, **k):
            called["cred"] = True

        async def get_token(self, *a, **k):
            return _FakeToken()

        async def close(self):
            return None

    # retrieve() imports DefaultAzureCredential from azure.identity.aio at call time; patch it there.
    import azure.identity.aio as _aio

    _orig = _aio.DefaultAzureCredential
    _aio.DefaultAzureCredential = _FakeCred  # type: ignore[assignment,misc]
    try:
        docs = await retrieval.retrieve("q", user=None, domain=_stub_domain())
    finally:
        _aio.DefaultAzureCredential = _orig  # type: ignore[assignment,misc]

    assert [d["index"] for d in docs] == [1, 2], docs  # deduped to 2, reindexed 1-based
    assert docs[0] == {"index": 1, "source": "a.md", "url": "https://x/a.md", "snippet": "S1"}, docs[0]
    assert docs[1] == {"index": 2, "source": "b.md", "url": "https://x/b.md", "snippet": "S2"}, docs[1]
    assert all("snippet" in d for d in docs), docs  # snippet present on every projected doc

    print("✅ retrieve() contract holds (native path patched; deduped-by-url + 1-based reindex)")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
