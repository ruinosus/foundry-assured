"""Nothing may sit in `knowledge/wiki-bundle/` that the knowledge base should not serve.

`ingest_docbundles.collect_pages` walks `knowledge/wiki-bundle/**` with `rglob("manifest.json")` and uploads
whatever it finds. There is no filter and no date check: whatever is on the shelf is in the
knowledge base. Meanwhile `wiki_fidelity_test` runs ONCE, at generation, on ONE bundle. Between
those two facts a bundle can rot on the shelf for months and keep being served as current.

Both halves of that happened here, and they failed differently — which is why this gate asks two
questions in this order:

**1. Does the bundle belong to the current generation model?** Four per-area bundles
(`foundry-helpdesk-{backend,frontend,infra,docs}`) predate the move to one bundle for the whole
repository. `wiki_freshness_test._RETIRED` already excuses them from grading — "kept for history"
— while `collect_pages` kept feeding them to the knowledge base. The repository called them
history and the agent read them as current, which is the worst of both readings.

**2. Only then: is it faithful?** Same floor and same implementation as the generation-time gate.

The order is the lesson. Three of those retired bundles scored 81.5%, 96.2% and 96.2%, and were
still wrong: they said "Next.js 15" (it is 16), "ADRs 001–011" (they run to 018), "4 domains"
(there are 5). Fidelity asks whether a citation RESOLVES, not whether the sentence around it is
still TRUE — a page can cite `main.bicep`, which certainly exists, and describe it as it was a
generation ago. A high score is not freshness, and treating it as such kept 25 stale pages in the
base. Only the other two failed on fidelity proper (27.5%, 36.7%), because ADR-017 moved the
backend files out from under their citations.

Offline and deterministic: reads the committed bundles and the working tree, talks to nothing.
Reuses `_fidelity_report` / `_fidelity_floor` from `wiki_builder` and `_AREA` / `_RETIRED` from
`wiki_freshness_test` — there must be exactly one answer to "is this wiki current and faithful",
or the answers drift apart and the shelf is where they hide.

    uv run python -m eval.wiki_shelf_test
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import app as _app
from app.modules.knowledge.internal.wiki_builder import (
    _fidelity_floor,
    _fidelity_report,
    gather_source,
)

REPO_ROOT = Path(_app.__file__).resolve().parents[3]
WIKI_ROOT = REPO_ROOT / "knowledge" / "wiki-bundle"

# Two questions, and the FIRST one matters more.
#
# 1. Does this bundle belong to the CURRENT generation model? `_AREA` (wiki_freshness_test) is the
#    single source of truth: one component, the whole repository. Bundles from the retired
#    per-area model are still on disk and — this is the bug — still ingested. The freshness gate
#    already excuses them from grading ("retired per-area bundles, kept for history"), so the repo
#    calls them history while `collect_pages` feeds them to the knowledge base as current.
#
#    They score WELL on fidelity (96.2%) and are still wrong: fidelity asks whether a citation
#    resolves, not whether the sentence around it is still true. Those bundles say "Next.js 15",
#    "ADRs 001–011", "4 domains" — every citation lands, every claim is out of date. They also
#    duplicate the current bundle, which covers the same infra and frontend ground.
#
# 2. Only then: is it faithful? Same floor, same implementation as the generation-time gate.
from eval.wiki_freshness_test import _AREA, _RETIRED


def _pages(manifest_path: Path, meta: dict) -> list[dict]:
    """The bundle's pages in the shape `_fidelity_report` expects (`{"content": ...}`)."""
    out: list[dict] = []
    for page in meta.get("pages") or []:
        f = manifest_path.parent / page.get("file", f"pages/{page.get('id')}.md")
        if f.exists():
            out.append({"content": f.read_text(encoding="utf-8")})
    return out


def main() -> int:
    if not WIKI_ROOT.is_dir():
        print(f"⏭️  no bundles under {WIKI_ROOT} — SKIPPED")
        return 0

    manifests = sorted(WIKI_ROOT.rglob("manifest.json"))
    if not manifests:
        print(f"⏭️  no bundles under {WIKI_ROOT} — SKIPPED")
        return 0

    floor = _fidelity_floor()
    files = gather_source(REPO_ROOT)  # ~6s for this repo; done once for every bundle
    print(f"Piso: {floor:.0%} · fonte: {len(files)} arquivos · {len(manifests)} bundle(s)\n")

    failures: list[tuple[str, float, int]] = []
    retired: list[tuple[str, int]] = []

    for manifest_path in manifests:
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        component = meta.get("component")
        name = f"{component}/{manifest_path.parent.name}"
        pages = _pages(manifest_path, meta)
        if not pages:
            continue

        if component in _RETIRED or component not in _AREA:
            # Retired model, still being ingested. Fidelity is beside the point.
            retired.append((name, len(pages)))
            print(f"  ✗ {name:<44} {len(pages):>3} páginas  — modelo APOSENTADO, mas ingerido")
            continue

        score = _fidelity_report(pages, files)["score"]
        ok = score + 1e-9 >= floor
        print(f"  {'✓' if ok else '✗'} {name:<44} {len(pages):>3} páginas  {score:>6.1%}")
        if not ok:
            failures.append((name, score, len(pages)))

    if retired:
        pages_lost = sum(n for _, n in retired)
        print(
            f"\n❌ {len(retired)} bundle(s) do modelo APOSENTADO ainda em knowledge/wiki-bundle/, somando\n"
            f"   {pages_lost} páginas. O gate de freshness já os lista como \"kept for history\" e\n"
            "   não os avalia — mas `collect_pages` varre knowledge/wiki-bundle/** e os envia para a base do\n"
            "   mesmo jeito. O repositório os chama de histórico; a KB os serve como atuais.\n\n"
            "   Eles passam em fidelidade e continuam errados: fidelidade pergunta se a citação\n"
            "   resolve, não se a frase em volta ainda é verdade.\n\n"
            "   Remova-os de knowledge/wiki-bundle/ (o git preserva o histórico).\n"
        )

    if failures:
        pages_lost = sum(n for _, _, n in failures)
        print(
            f"\n❌ {len(failures)} bundle(s) abaixo do piso, somando {pages_lost} páginas que a\n"
            "   ingestão enviaria para a base assim mesmo — `collect_pages` varre knowledge/wiki-bundle/**\n"
            "   inteiro e não consulta este gate.\n\n"
            "   Regenere o bundle, ou remova-o de knowledge/wiki-bundle/. Remover o arquivo NÃO limpa uma\n"
            "   base já indexada: é preciso reingerir para que _prune_stale_blobs + purge_orphans\n"
            "   apaguem os blobs e os chunks correspondentes.\n"
        )
        return 1

    if retired:
        return 1

    print("\n✅ todo bundle commitado pertence ao modelo atual e continua fiel ao código.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
