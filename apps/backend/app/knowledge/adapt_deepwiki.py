"""Adapt a GitHub Copilot CLI **deep-wiki** output into our ingest bundle format.

The "second generation path" (see docs/SECOND-DOMAIN-WIKI-PLAN.md → *Two generation
paths*): instead of the Foundry `wiki_builder.py`, a developer runs Microsoft's native
`deep-wiki` plugin in the GitHub Copilot CLI:

    cd <repo>
    copilot
      /plugin marketplace add microsoft/skills
      /plugin install deep-wiki@skills
      /deep-wiki:crisp        # 5–8 markdown pages, rate-limit friendly, no VitePress build

deep-wiki writes pages under `wiki/**/*.md` (source-linked citations) + `llms.txt` at
the repo root. This adapter maps that into the same bundle our ingestion already reads
(`manifest.json` + `pages/page-N.md` + `llms.txt`), so the Copilot-generated wiki flows
into the SAME Foundry IQ `cockpit-kb`. Generator is recorded in the manifest `model`
field so the two paths are distinguishable.

Output structure (per ingest_cockpit.collect_pages):
    <out>/<component>/<version>/{manifest.json, pages/page-N.md, llms.txt}

NOTE: the deep-wiki output layout (wiki/**/*.md + root llms.txt) is taken from the
plugin docs; this adapter is tolerant (configurable --wiki-dir, llms.txt ordering with
a sorted-path fallback) so it survives layout drift. Verify against your real run.

Run:
    cd apps/backend
    uv run python -m app.knowledge.adapt_deepwiki \
        --repo /path/to/your/repo \
        --component your-component --version vX.Y.Z \
        --out /tmp/wiki-out-copilot
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# Nav/scaffold files deep-wiki may emit that are not content pages.
_SKIP_NAMES = {"_sidebar.md", "summary.md", "index.md", "readme.md", "llms.txt", "llms-full.txt"}
_SKIP_DIRS = {".vitepress", "onboarding", "node_modules", ".git"}
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)[^)]*\)")  # markdown link to a .md file


def _resolve_wiki_dir(repo: Path, wiki_dir: str | None) -> Path:
    if wiki_dir:
        d = Path(wiki_dir).expanduser().resolve()
        if not d.is_dir():
            raise SystemExit(f"--wiki-dir not found: {d}")
        return d
    for cand in (repo / "wiki", repo / "docs" / "wiki", repo):
        if cand.is_dir() and any(cand.rglob("*.md")):
            return cand
    raise SystemExit(f"No wiki/*.md found under {repo}. Pass --wiki-dir explicitly.")


def _title_of(md_text: str, fallback: str) -> str:
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def _ordered_pages(wiki_dir: Path, llms_path: Path | None) -> list[Path]:
    """Content pages in reading order: follow llms.txt links when present, else sort."""
    pages = [
        p for p in wiki_dir.rglob("*.md")
        if p.name.lower() not in _SKIP_NAMES
        and not any(part in _SKIP_DIRS for part in p.parts)
        and not p.name.startswith("_")
    ]
    if not pages:
        raise SystemExit(f"No content pages under {wiki_dir}")
    by_name = {p.name.lower(): p for p in pages}
    by_rel = {str(p.relative_to(wiki_dir)).lower(): p for p in pages}

    ordered: list[Path] = []
    if llms_path and llms_path.exists():
        seen: set[Path] = set()
        for m in _LINK_RE.finditer(llms_path.read_text(encoding="utf-8", errors="ignore")):
            ref = m.group(1).strip().lstrip("./").lower()
            hit = by_rel.get(ref) or by_name.get(Path(ref).name)
            if hit and hit not in seen:
                ordered.append(hit)
                seen.add(hit)
        # append any content page not referenced by llms.txt
        ordered += [p for p in sorted(pages) if p not in seen]
        return ordered
    return sorted(pages)


def adapt(repo: Path, component: str, version: str, out_dir: Path, wiki_dir: str | None, language: str) -> Path:
    wd = _resolve_wiki_dir(repo, wiki_dir)
    llms = next((c for c in (repo / "llms.txt", wd / "llms.txt") if c.exists()), None)
    page_files = _ordered_pages(wd, llms)
    print(f"  wiki dir: {wd}  ({len(page_files)} content pages)", flush=True)

    bundle = out_dir / component / version
    (bundle / "pages").mkdir(parents=True, exist_ok=True)
    manifest_pages, llms_lines = [], [f"# {component} {version}\n"]
    for order, src in enumerate(page_files, 1):
        norm = f"page-{order}"
        body = src.read_text(encoding="utf-8", errors="ignore")
        title = _title_of(body, src.stem.replace("-", " ").title())
        (bundle / "pages" / f"{norm}.md").write_text(body, encoding="utf-8")
        manifest_pages.append(
            {"id": norm, "title": title, "order": order, "file": f"pages/{norm}.md", "audience": "base"}
        )
        llms_lines.append(f"- [{title}](pages/{norm}.md)")
        print(f"  ✓ page {order}/{len(page_files)}: {title}  (← {src.name})", flush=True)

    manifest = {
        "key": f"{component}-{version}", "title": f"{component} {version}",
        "source": {"type": "repo", "ref": str(repo), "commit": ""},
        "language": language, "model": "github-copilot-cli/deep-wiki",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "element", "component": component, "componentVersion": version,
        "releaseVersion": None, "pages": manifest_pages,
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (bundle / "llms.txt").write_text("\n".join(llms_lines) + "\n", encoding="utf-8")
    print(f"\n✅ Bundle (deep-wiki → ingest format): {bundle}  ({len(manifest_pages)} páginas)", flush=True)
    return bundle


def main() -> None:
    ap = argparse.ArgumentParser(description="Adapt a Copilot CLI deep-wiki output into the ingest bundle format.")
    ap.add_argument("--repo", required=True, help="Repo where deep-wiki ran (contains wiki/ + llms.txt)")
    ap.add_argument("--component", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", default="/tmp/wiki-out-copilot")
    ap.add_argument("--wiki-dir", default=None, help="Override the wiki pages dir (default: <repo>/wiki)")
    ap.add_argument("--language", default="pt-br")
    args = ap.parse_args()
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    adapt(repo, args.component, args.version, Path(args.out).expanduser(), args.wiki_dir, args.language)


if __name__ == "__main__":
    main()
