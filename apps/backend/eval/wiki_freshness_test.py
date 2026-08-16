"""Wiki-freshness gate — the deep-wiki must track the code.

The build-fidelity gate proves the wiki is faithful *at generation*. This proves it stays
faithful *over time*: for each generated bundle in knowledge/wiki-bundle/<component>/<version>, compare its
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
_WIKI = _ROOT / "knowledge" / "wiki-bundle"

# Generated component → the source area it was built from (relative to the repo root).
#
# ONE component, the whole repository. The four per-area bundles that came before were removed
# from the shelf — see _RETIRED below for why removal, not merely un-grading, was the fix.
#
# Why the split ended: OpenWiki keeps a single `openwiki/` for a repository, while the bundles
# were per-area. The first area worked (an --init into an empty directory); the second would have
# run `--update` against a wiki about a DIFFERENT area, with the generator scoped away from the
# very files that wiki describes. One wiki out, one bundle in, and the mismatch disappears.
_AREA = {
    "foundry-assured": ".",
}

# Retired components, no longer on disk. They were "kept for history and still in the KB,
# deliberately NOT graded", and that half-measure was the bug: un-grading them stopped the gate
# from going permanently red, but `collect_pages` walks the shelf unconditionally, so the
# knowledge base kept serving them as current. The repository called them history; the agent
# cited them as fact. Three scored above the fidelity floor and were stale anyway ("Next.js 15",
# "ADRs 001–011") — proof that a good fidelity score is not freshness.
#
# The list stays as a TRIPWIRE, not as documentation: `wiki_shelf_test` fails if any of these
# reappears under knowledge/wiki-bundle/, so restoring one from git cannot quietly re-enter the KB.
# The bundles themselves live in git history, which is where history belongs.
_RETIRED = {
    "foundry-helpdesk-backend",
    "foundry-helpdesk-frontend",
    "foundry-helpdesk-infra",
    "foundry-helpdesk-docs",
}


# Everything `wiki-regen.yml` writes back to the repository. Excluded from "did the source
# change?", because a generator's own output is not source — counting it makes the gate
# unsatisfiable: regenerating the wiki becomes the very change that marks it stale.
#
# `openwiki/` was missing here and that is exactly what happened. The bundle was generated at
# 20:14:54 and the commit carrying it landed at 20:17:51 — one commit holding BOTH the bundle
# and openwiki/ — so the check compared the wiki against a "source change" that was the wiki.
# Measured against the real last source commit (#157, 20:10:25) the bundle is newer, which is
# the truth. The docstring below already stated this intent; only `openwiki/` post-dated it.
_GENERATED = (":(exclude)knowledge/wiki-bundle", ":(exclude)openwiki")


def _latest_commit_iso(area: str) -> str | None:
    """Latest commit date touching `area`, EXCLUDING everything the generator writes (so
    regenerating the wiki doesn't make the bundle look perpetually stale)."""
    args = ["git", "-C", str(_ROOT), "log", "-1", "--format=%cI", "--",
            area, *_GENERATED]
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
        print("⏭️  no knowledge/wiki-bundle — nothing to check.")
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
              "(see knowledge/README.md), and commit the refreshed bundle.")
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
