"""Fidelity gate for a wiki bundle that was generated ELSEWHERE.

`wiki_builder` already gates its own output at generation time. A bundle produced by an
external generator (`adapt_deepwiki`, `adapt_openwiki` — ADR-012/016) never passes through
that code, so it needs the same check applied from outside, using the same function and the
same floor: no second implementation of "is this wiki faithful", because two implementations
drift and the lenient one wins.

What it measures (`wiki_builder._fidelity_report`): the fraction of the bundle's file
citations that resolve to a real source file, and whether any citation points into a
worktree. Below `build.fidelity_min` (eval/assurance.yaml) — or with a single worktree
citation — the bundle must not reach the knowledge base.

This is the gate that matters MORE once regeneration is automated: with a bot writing the
wiki unattended, it is the only thing between a hallucinated page and the KB users query.

Run (from apps/backend):
    uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend
    uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend --version v0.4.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.knowledge.wiki_builder import _fidelity_floor, _fidelity_report, gather_source

REPO_ROOT = Path(__file__).resolve().parents[3]
WIKI_ROOT = REPO_ROOT / "docs" / "wiki"


def _latest_version(component_dir: Path) -> Path:
    """Newest bundle version for a component. Sorted lexically, which is what `vYYYYMMDD`
    and `vX.Y.Z` both want in practice; an explicit --version wins when it does not."""
    versions = sorted((p for p in component_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
    if not versions:
        raise SystemExit(f"❌ no bundle versions under {component_dir}")
    return versions[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fidelity gate for an externally generated wiki bundle.")
    ap.add_argument("--component", required=True, help="Bundle component (e.g. foundry-helpdesk-backend).")
    ap.add_argument("--version", default=None, help="Bundle version (default: the newest present).")
    args = ap.parse_args()

    component_dir = WIKI_ROOT / args.component
    if not component_dir.is_dir():
        raise SystemExit(f"❌ no such component bundle: {component_dir}")
    bundle = (component_dir / args.version) if args.version else _latest_version(component_dir)

    pages_dir = bundle / "pages"
    if not pages_dir.is_dir():
        raise SystemExit(f"❌ no pages/ in {bundle}")
    pages = [
        {"title": p.stem, "content": p.read_text(encoding="utf-8")}
        for p in sorted(pages_dir.glob("*.md"))
    ]
    if not pages:
        raise SystemExit(f"❌ no pages in {pages_dir}")

    fid = _fidelity_report(pages, gather_source(REPO_ROOT))
    floor = _fidelity_floor()

    print(f"Bundle : {bundle.relative_to(REPO_ROOT)}  ({len(pages)} páginas)")
    print(
        f"Fidelity: {fid['score']:.1%} — {fid['resolved']}/{fid['total']} citações resolvem para "
        f"arquivo real | {fid['distinct']} arquivos distintos, {fid['worktree']} em worktree"
    )
    print(f"Floor  : {floor:.0%}")

    if fid["worktree"]:
        print(f"\n❌ {fid['worktree']} citação(ões) apontam para um worktree — o bundle não pode ser ingerido.")
        return 1
    if fid["score"] + 1e-9 < floor:
        print(f"\n❌ Fidelity {fid['score']:.1%} abaixo do piso {floor:.0%} — o bundle não pode ser ingerido.")
        return 1
    print("\n✅ Fidelity gate passou — o bundle pode ser ingerido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
