"""Round-trip test for the ACL chunk attribution (review finding #1).

The trim only keeps a chunk if its component (from the chunk's H1) is in the caller's
authorized set (from blob URLs). Those two derivations MUST agree, or authorized content
is silently over-trimmed. This asserts `_chunk_component(H1) == _component(blob)` for the
representative shapes — especially the platform bundle, where the blob key is kebab
(`plataforma-techdocs-2.1.0`) but the H1 is a human title (`Plataforma TechDocs 2.1.0`).

    uv run python -m eval.test_attribution
"""

from __future__ import annotations

import sys

from app.modules.knowledge.internal.secure_search import _chunk_component
from app.modules.knowledge.internal.acl_setup import _component

# (blob name, chunk H1) → must resolve to the same component key.
_CASES = [
    ("techdocs-mcp-agent-v1.2.0__page-2.md", "# techdocs-mcp-agent v1.2.0 — Arquitetura Geral"),
    ("techdocs-portal-api-v2.1.1__page-3.md", "# techdocs-portal-api v2.1.1 — Arquitetura"),
    ("plataforma-techdocs-2.1.0__page-1.md", "# Plataforma TechDocs 2.1.0 — Visão Geral"),
    ("techdocs-mcp-sdk-v1.0.0__page-1.md", "# techdocs-mcp-sdk v1.0.0 — Visão Geral"),
    ("source__ARCHITECTURE__page-1.md", "# TechDocs (fonte): Architecture"),
    ("source__TECHDOCS_OVERVIEW__page-1.md", "# TechDocs (fonte): TechDocs Overview"),
]


def main() -> int:
    failures = []
    for blob, h1 in _CASES:
        a, b = _component(blob), _chunk_component(h1)
        ok = a == b
        print(f"  {'✓' if ok else '✗'} {a!r:40} == {b!r}")
        if not ok:
            failures.append((blob, h1, a, b))
    if failures:
        print(f"\n❌ {len(failures)} attribution mismatch(es) — the trim would over-restrict these.")
        return 1
    print("\n✅ attribution round-trips: every chunk maps to the same key as its blob.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
