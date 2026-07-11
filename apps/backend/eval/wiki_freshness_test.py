"""Wiki-freshness gate — the deep-wiki must track the code.

The build-fidelity gate proves the wiki is faithful *at generation*. This proves it stays
faithful *over time*: for each generated bundle in docs/wiki/<component>/<version>, compare its
`generatedAt` against the latest git commit touching that area's source. If the source is
newer, the wiki is stale and must be regenerated (wiki_builder + re-ingest) — otherwise the
agent grounds in a wiki that no longer matches the code.

Not wired as a required merge gate (regeneration needs the Foundry model, not available in
basic CI) — it runs as its own workflow so staleness is *visible*. Run locally any time:

    uv run python -m eval.wiki_freshness_test
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_WIKI = _ROOT / "docs" / "wiki"

# Generated component → the source area it was built from (relative to the repo root).
_AREA = {
    "foundry-helpdesk-backend": "apps/backend",
    "foundry-helpdesk-frontend": "apps/frontend",
    "foundry-helpdesk-infra": "infra",
    "foundry-helpdesk-docs": "docs",
}


def _latest_commit_iso(area: str) -> str | None:
    """Latest commit date touching `area`, EXCLUDING the generated wiki itself (so
    regenerating docs/wiki doesn't make the docs bundle look perpetually stale)."""
    args = ["git", "-C", str(_ROOT), "log", "-1", "--format=%cI", "--",
            area, ":(exclude)docs/wiki"]
    out = subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()
    return out or None


def main() -> int:
    if not _WIKI.exists():
        print("⏭️  no docs/wiki — nothing to check.")
        return 0
    stale: list[tuple[str, str, str, str]] = []
    checked = 0
    for manifest in sorted(_WIKI.rglob("manifest.json")):
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        comp = meta.get("component") or manifest.parent.parent.name
        gen = meta.get("generatedAt")
        area = _AREA.get(comp)
        if not (gen and area):
            continue
        commit = _latest_commit_iso(area)
        if not commit:
            continue
        checked += 1
        if datetime.fromisoformat(commit) > datetime.fromisoformat(gen):
            stale.append((comp, area, gen, commit))

    if stale:
        print("❌ Wiki STALE — source changed after the wiki was generated:\n")
        for comp, area, gen, commit in stale:
            print(f"   {comp}: {area} last changed {commit}  >  wiki generated {gen}")
        print("\n   → regenerate: wiki_builder --repo <area> … then re-ingest "
              "(see docs/wiki/README.md), and commit the refreshed bundle.")
        return 1
    print(f"✅ Wiki fresh — all {checked} bundle(s) newer than their source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
