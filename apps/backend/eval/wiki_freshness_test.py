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

import app as _app

_ROOT = Path(_app.__file__).resolve().parents[3]
_WIKI = _ROOT / "docs" / "wiki"

# Generated component → the source area it was built from (relative to the repo root).
#
# ONE component, the whole repository. The four per-area bundles that came before are still on
# disk and still ingested, but they are no longer graded — see _RETIRED below.
#
# Why the split ended: OpenWiki keeps a single `openwiki/` for a repository, while the bundles
# were per-area. The first area worked (an --init into an empty directory); the second would have
# run `--update` against a wiki about a DIFFERENT area, with the generator scoped away from the
# very files that wiki describes. One wiki out, one bundle in, and the mismatch disappears.
_AREA = {
    "foundry-assured": ".",
}

# Bundles kept for history and still in the KB, deliberately NOT graded: their source areas moved
# under the single-bundle model, so grading them would report drift that nobody can ever fix —
# a permanently red gate, which is how this repository lost eight weeks of signal once already.
# They are LISTED in the output rather than skipped in silence: "not graded" must be visible, or
# it reads as "checked and fine".
_RETIRED = {
    "foundry-helpdesk-backend",
    "foundry-helpdesk-frontend",
    "foundry-helpdesk-infra",
    "foundry-helpdesk-docs",
}


def _latest_commit_iso(area: str) -> str | None:
    """Latest commit date touching `area`, EXCLUDING the generated wiki itself (so
    regenerating docs/wiki doesn't make the docs bundle look perpetually stale)."""
    args = ["git", "-C", str(_ROOT), "log", "-1", "--format=%cI", "--",
            area, ":(exclude)docs/wiki"]
    out = subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()
    return out or None


def area_path(component: str) -> str:
    """Source area a component's wiki is built from. Queryable so wiki-regen.yml can scope the
    generator to one area without a second copy of `_AREA` living in YAML — two copies of a map
    is two things to forget to update, and the one in YAML is the one nobody tests."""
    area = _AREA.get(component)
    if not area:
        raise SystemExit(f"❌ unknown component: {component} (known: {', '.join(sorted(_AREA))})")
    return area


def main() -> int:
    # `--path-for <component>` answers "which directory is this wiki about?" and exits. It is a
    # query, not a gate run.
    if len(sys.argv) == 3 and sys.argv[1] == "--path-for":
        print(area_path(sys.argv[2]))
        return 0

    if not _WIKI.exists():
        print("⏭️  no docs/wiki — nothing to check.")
        return 0
    stale: list[tuple[str, str, str, str]] = []
    retired: set[str] = set()
    checked = 0
    for manifest in sorted(_WIKI.rglob("manifest.json")):
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        comp = meta.get("component") or manifest.parent.parent.name
        gen = meta.get("generatedAt")
        if comp in _RETIRED:
            retired.add(comp)
            continue
        area = _AREA.get(comp)
        if not (gen and area):
            continue
        commit = _latest_commit_iso(area)
        if not commit:
            continue
        checked += 1
        if datetime.fromisoformat(commit) > datetime.fromisoformat(gen):
            stale.append((comp, area, gen, commit))

    if retired:
        print(f"ℹ️  not graded (retired per-area bundles, kept for history): {', '.join(sorted(retired))}\n")

    if stale:
        print("❌ Wiki STALE — source changed after the wiki was generated:\n")
        for comp, area, gen, commit in stale:
            print(f"   {comp}: {area} last changed {commit}  >  wiki generated {gen}")
        print("\n   → regenerate: wiki_builder --repo <area> … then re-ingest "
              "(see docs/wiki/README.md), and commit the refreshed bundle.")
        return 1
    if not checked:
        # "0 bundles checked, all fresh" is a pass that means nothing — the failure mode this
        # workflow exists to avoid. With no gradable bundle the honest answer is the same as
        # drift, and it is also the useful one: this output drives wiki-regen, and "no wiki yet"
        # is precisely when regeneration should run.
        print(f"❌ No gradable bundle for {', '.join(sorted(_AREA))} — nothing documents the repository yet.")
        return 1
    print(f"✅ Wiki fresh — all {checked} bundle(s) newer than their source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
