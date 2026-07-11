"""Round-trip test for the ACL chunk attribution (review finding #1).

The trim only keeps a chunk if its component (from the chunk's H1) is in the caller's
authorized set (from blob URLs). Those two derivations MUST agree, or authorized content
is silently over-trimmed. This asserts `_chunk_component(H1) == _component(blob)` for the
representative shapes — especially the platform bundle, where the blob key is kebab
(`plataforma-cockpit-2.1.0`) but the H1 is a human title (`Plataforma Cockpit 2.1.0`).

    uv run python -m eval.test_attribution
"""

from __future__ import annotations

import sys

from app.agents.secure_search import _chunk_component
from app.knowledge.acl_setup import _component

# (blob name, chunk H1) → must resolve to the same component key.
_CASES = [
    ("cockpit-mcp-agent-v1.2.0__page-2.md", "# cockpit-mcp-agent v1.2.0 — Arquitetura Geral"),
    ("cockpit-portal-api-v2.1.1__page-3.md", "# cockpit-portal-api v2.1.1 — Arquitetura"),
    ("plataforma-cockpit-2.1.0__page-1.md", "# Plataforma Cockpit 2.1.0 — Visão Geral"),
    ("cockpit-mcp-sdk-v1.0.0__page-1.md", "# cockpit-mcp-sdk v1.0.0 — Visão Geral"),
    ("source__ARCHITECTURE__page-1.md", "# Cockpit (fonte): Architecture"),
    ("source__COCKPIT_OVERVIEW__page-1.md", "# Cockpit (fonte): Cockpit Overview"),
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
