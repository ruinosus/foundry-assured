"""Adapt an **OpenWiki** output into our ingest bundle format.

The third generation path (ADR-016). `adapt_deepwiki.py` already does this for the
Copilot CLI deep-wiki output; OpenWiki becomes another producer behind the same
seam rather than a second format:

    npm install -g openwiki
    cd <repo>
    openwiki code --update --print          # writes openwiki/**/*.md (OKF v0.2 desde 0.4.0)

OpenWiki writes Markdown with YAML front matter under `openwiki/`, plus navigation
(`index.md` per directory), scaffold files (`_skeleton.md`, `_plan.md`) and a run
receipt (`.last-update.json`). This maps the content pages into the bundle every
ingest already reads (`manifest.json` + `pages/page-N.md` + `llms.txt`), so an
OpenWiki-generated wiki flows into the SAME Foundry IQ knowledge base.

Two things travel out of the OpenWiki output rather than being invented here:
the **commit** it documented and the **model** that wrote it, both read from
`.last-update.json`. The manifest's `model` field records the producer so the
three paths stay distinguishable in the KB.

Front matter TRAVELS WITH THE PAGE: `okf_version`, `tags`, `type`, and — since OKF
v0.2 — `generated {by,at}`, `verified [{by,at}]` and `sources [{id,resource}]` are
exactly the trust signals this product wants, and they are written verbatim into
`pages/page-N.md` ahead of the body. The `title` is lifted out of it first
(`_title_of`, unchanged).

It is retrieval text that must not carry YAML, not the bundle file, so the strip
happens at index time in `ingest_docbundles.collect_pages` — the one place that
turns a page into the corpus a model can cite. Doing it here would make the block
survive the write but still never reach anyone, since nothing else reads it.

`docbundle.schema.json` never governed this: it is a vendored contract over
`manifest.json` — 13 properties, all manifest fields, zero occurrences of
`content`/`body`/`frontmatter`/`hash` — so there was never a field to diverge from
and no sidecar file is needed. Measured and recorded in
`docs/superpowers/specs/2026-08-27-openwiki-claims-medicao.md` §5.4, which proves
real v0.2 front matter survives `_split_front_matter` without leaking YAML into the
body it returns.

Output structure (per ingest_docbundles.collect_pages):
    <out>/<component>/<version>/{manifest.json, pages/page-N.md, llms.txt}

Run (from apps/backend):
    uv run python -m app.modules.knowledge.internal.adapt_openwiki \
        --repo /path/to/your/repo \
        --component foundry-helpdesk-backend --version v0.4.0 \
        --out /tmp/wiki-out-openwiki
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.modules.knowledge.internal import frontmatter
from app.modules.knowledge.internal.docbundle_schema import validate_manifest

# Navigation and scaffold files OpenWiki emits that are not content pages.
# `index.md` is per-directory navigation; `_skeleton.md`/`_plan.md` are run scaffolding
# (the agent clears the skeleton after init but leaves the file); `INSTRUCTIONS.md` is the
# user-authored scope input, not output; `log.md` is a reserved OKF document.
_SKIP_NAMES = {"index.md", "_skeleton.md", "_plan.md", "instructions.md", "log.md", "readme.md"}
_SKIP_DIRS = {".git", "node_modules"}
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)[^)]*\)")  # markdown link to a .md file
_LINK_SUB_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)[^)]*\)")  # same, with the text captured
_FM_TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)


def _resolve_wiki_dir(repo: Path, wiki_dir: str | None) -> Path:
    """Where the OpenWiki output lives. `openwiki/` is its code-mode default."""
    if wiki_dir:
        wd = (repo / wiki_dir) if not Path(wiki_dir).is_absolute() else Path(wiki_dir)
        if not wd.is_dir():
            raise SystemExit(f"❌ --wiki-dir not found: {wd}")
        return wd
    wd = repo / "openwiki"
    if not wd.is_dir():
        raise SystemExit(
            f"❌ no OpenWiki output at {wd}. Run `openwiki code --update` in the repo first, "
            "or point --wiki-dir at the directory."
        )
    return wd


def _split_front_matter(md_text: str) -> tuple[str, str]:
    """Return (front_matter, body). Front matter is OKF metadata, not page content.

    Delegates to `frontmatter.split` so this repo has ONE parser for the format: the same
    separation lived here, in the corpus ingest, and in a gate, and three copies of a parser
    diverge on the first new shape — silently, because each one simply stops seeing what the
    others see. `split` (not `parse`) on purpose: this path only lifts a title, so a malformed
    block must not stop the page from being adapted."""
    cru, corpo = frontmatter.split(md_text)
    return (f"---\n{cru}\n---\n" if cru else ""), corpo


def _title_of(front_matter: str, body: str, fallback: str) -> str:
    """Front-matter `title` wins; then the first H1; then the filename."""
    fm = _FM_TITLE_RE.search(front_matter)
    if fm:
        return fm.group(1).strip().strip("\"'")
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _ordered_pages(wiki_dir: Path) -> list[Path]:
    """Content pages in navigation order.

    OpenWiki writes an `index.md` per directory listing its pages; walking those links
    preserves the order a reader would follow. Anything the indexes miss is appended in
    sorted order so a page is never silently dropped — the alternative (trusting nav to be
    complete) is how a generator quietly loses a page.
    """
    def is_content(p: Path) -> bool:
        return (
            p.suffix == ".md"
            and p.name.lower() not in _SKIP_NAMES
            and not any(part in _SKIP_DIRS for part in p.parts)
        )

    ordered: list[Path] = []
    seen: set[Path] = set()
    for index in sorted(wiki_dir.rglob("index.md"), key=lambda p: len(p.parts)):
        for rel in _LINK_RE.findall(index.read_text(encoding="utf-8", errors="ignore")):
            target = (index.parent / rel).resolve()
            if target.is_file() and is_content(target) and target not in seen:
                ordered.append(target)
                seen.add(target)

    for p in sorted(wiki_dir.rglob("*.md")):
        rp = p.resolve()
        if is_content(rp) and rp not in seen:
            ordered.append(rp)
            seen.add(rp)
    return ordered


def _flatten_internal_links(body: str) -> str:
    """Reduce wiki-to-wiki links to their text. Deliberate, and measured.

    OpenWiki pages navigate to each other (`[Grounded domains](grounded-domains.md)`). Two
    reasons those links do not belong in an ingest bundle:

    1. **They corrupt the fidelity measurement.** The gate treats any `something.md` token as a
       file citation, so an inter-page link counts as a citation — one that resolves only while
       the wiki files happen to sit in the scanned tree. Measured here: the raw output scored
       99.3% against the worktree and 81.0% against the real source, and the gap was 28 distinct
       phantom citations, not a quality difference.
    2. **Rewriting them to `page-N.md` does not help** — that was tried; the renamed targets are
       not source files either, so 27 phantoms simply came back under new names (92.6%, still
       inflated by noise rather than earned).

    The bundle is a retrieval artifact: pages are chunked and surfaced individually, so
    page-to-page navigation buys nothing there while distorting the one number that decides
    whether the wiki may reach the KB. The prose survives; only the link does not.
    """
    return _LINK_SUB_RE.sub(lambda m: m.group(1), body)


def _run_receipt(wiki_dir: Path) -> dict:
    """`.last-update.json` — the commit OpenWiki documented and the model that wrote it."""
    receipt = wiki_dir / ".last-update.json"
    if not receipt.is_file():
        return {}
    try:
        return json.loads(receipt.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def adapt(repo: Path, component: str, version: str, out_dir: Path, wiki_dir: str | None, language: str) -> Path:
    wd = _resolve_wiki_dir(repo, wiki_dir)
    page_files = _ordered_pages(wd)
    if not page_files:
        raise SystemExit(f"❌ no content pages under {wd} (only nav/scaffold files?).")
    receipt = _run_receipt(wd)
    print(f"  wiki dir: {wd}  ({len(page_files)} content pages)", flush=True)
    if receipt:
        print(f"  run receipt: commit={receipt.get('gitHead', '')[:12]} model={receipt.get('model', '?')}", flush=True)

    bundle = out_dir / component / version
    (bundle / "pages").mkdir(parents=True, exist_ok=True)
    manifest_pages, llms_lines = [], [f"# {component} {version}\n"]
    for order, src in enumerate(page_files, 1):
        norm = f"page-{order}"
        front_matter, body = _split_front_matter(src.read_text(encoding="utf-8", errors="ignore"))
        title = _title_of(front_matter, body, src.stem.replace("-", " ").title())
        body = _flatten_internal_links(body)
        # O bloco viaja COM a página (gap G1 da auditoria de 2026-09-02). Ele é retirado em
        # `ingest_docbundles.collect_pages`, antes de virar texto indexado — que é onde o
        # descarte sempre pertenceu, e não aqui.
        (bundle / "pages" / f"{norm}.md").write_text(
            front_matter + body.lstrip("\n"), encoding="utf-8"
        )
        manifest_pages.append(
            {"id": norm, "title": title, "order": order, "file": f"pages/{norm}.md", "audience": "base"}
        )
        llms_lines.append(f"- [{title}](pages/{norm}.md)")
        print(f"  ✓ page {order}/{len(page_files)}: {title}  (← {src.relative_to(wd)})", flush=True)

    manifest = {
        "key": f"{component}-{version}",
        "title": f"{component} {version}",
        # The commit comes from OpenWiki's own receipt — the wiki claims to document THAT
        # tree, and the freshness gate compares against it. Inventing "HEAD now" would make
        # a stale bundle look current.
        "source": {"type": "repo", "ref": str(repo), "commit": receipt.get("gitHead", "")},
        "language": language,
        "model": f"openwiki/{receipt.get('model', 'unknown')}",
        "generatedAt": receipt.get("updatedAt")
        or datetime.now(UTC).isoformat(timespec="seconds"),
        "kind": "element",
        "component": component,
        "componentVersion": version,
        # Like the deep-wiki path, this generator has no access input (it knows nothing about
        # the repo's read groups), so it declares nothing. `null`, never `[]` — an empty list
        # would read as "no group may read", and the ingest is fail-closed.
        "releaseVersion": None,
        "groups": None,
        "pages": manifest_pages,
    }
    # Same contract as every other writer of this format (docbundle_schema.py).
    try:
        validate_manifest(manifest)
    except ValueError as exc:
        raise SystemExit(f"❌ {exc}") from exc
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (bundle / "llms.txt").write_text("\n".join(llms_lines) + "\n", encoding="utf-8")
    print(f"\n✅ Bundle (OpenWiki → ingest format): {bundle}  ({len(manifest_pages)} páginas)", flush=True)
    return bundle


def main() -> None:
    ap = argparse.ArgumentParser(description="Adapt an OpenWiki output into the ingest bundle format.")
    ap.add_argument("--repo", required=True, help="Repository root that OpenWiki ran in.")
    ap.add_argument("--component", required=True, help="Bundle component name (e.g. foundry-helpdesk-backend).")
    ap.add_argument("--version", required=True, help="Bundle version (e.g. v0.4.0).")
    ap.add_argument("--out", required=True, help="Output directory for the bundle tree.")
    ap.add_argument("--wiki-dir", default=None, help="Override the OpenWiki output dir (default: <repo>/openwiki).")
    ap.add_argument("--language", default="pt-br", help="Manifest language tag (default: pt-br).")
    args = ap.parse_args()
    adapt(Path(args.repo).resolve(), args.component, args.version, Path(args.out).resolve(),
          args.wiki_dir, args.language)


if __name__ == "__main__":
    main()
