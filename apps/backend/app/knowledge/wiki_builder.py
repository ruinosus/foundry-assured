"""Wiki Builder — generate a FAITHFUL LLM Wiki from source, on Foundry.

The "generate" side of the LLM Wiki pattern (see docs/SECOND-DOMAIN-WIKI-PLAN.md):
a Foundry agent reads the REAL source and writes a cited, bundle-format wiki
(manifest.json + pages/*.md + llms.txt), driven by the depth rules of Microsoft's
deep-wiki **wiki-page-writer** Agent Skill (MIT) — "trace actual code paths, every
claim cites a real file, no guessing". That faithfulness fixes the gaps of
LLM-summarized docs, automatically. Output = the format ingest_cockpit consumes.

Paced + bounded (read deterministically; one planner call + one call per page with a
small delay) so it stays under the model deployment's rate limit — agentic tool loops
burst over the TPM cap on a small deployment.

D1: one component. Run:
    cd apps/backend
    uv run python -m app.knowledge.wiki_builder \
        --repo /path/to/cockpit/cockpit-openai-loadbalancer \
        --component cockpit-openai-loadbalancer --version v1.1.0 --out /tmp/wiki-out
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.core.settings import settings

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent / "skills"
_IGNORE = {
    "node_modules", "bin", "obj", "packages", ".vs", "target", "vendor",
    ".terraform", "dist", "build", ".venv", "__pycache__", ".git", ".idea",
}
_SOURCE_EXT = {".cs", ".py", ".ts", ".tsx", ".js", ".go", ".java", ".json", ".yaml",
               ".yml", ".toml", ".md", ".csproj", ".sln", ".sql", ".sh", ".tf"}
_MAX_FILE_CHARS = 16_000
_PAGE_DELAY_S = 8  # pace page calls to stay under the model TPM cap


def gather_source(repo: Path) -> dict[str, str]:
    """Read the relevant source files (skipping build artifacts), path -> content."""
    files: dict[str, str] = {}
    for f in sorted(repo.rglob("*")):
        if not f.is_file() or any(p in _IGNORE for p in f.parts):
            continue
        if f.suffix.lower() not in _SOURCE_EXT and f.name.lower() not in ("readme", "dockerfile"):
            continue
        rel = str(f.relative_to(repo))
        text = f.read_text(encoding="utf-8", errors="ignore")
        files[rel] = text[:_MAX_FILE_CHARS]
    return files


def _writer_rules() -> str:
    """The depth rules from the installed Microsoft wiki-page-writer skill."""
    skill = _SKILLS_DIR / "wiki-page-writer" / "SKILL.md"
    return skill.read_text(encoding="utf-8") if skill.exists() else ""


_CTX_BUDGET = 40_000  # chars of source per page call — keep the prompt under the model limit
_PER_FILE = 8_000


def _page_context(files: dict[str, str], wanted: list[str]) -> str:
    """Bounded source context for one page: the planner's files (lenient match), then
    a small default, capped to a char budget so the call never times out."""
    def norm(s: str) -> str:
        return s.strip("./ ").lower()

    picked = [f for f in files if any(norm(w) and (norm(w) in f.lower() or f.lower() in norm(w)) for w in wanted)]
    if not picked:  # no match → README + a few files instead of ALL of them
        picked = sorted(files, key=lambda f: (0 if "readme" in f.lower() else 1, len(f)))[:6]
    parts, total = [], 0
    for fp in picked:
        snippet = files[fp][:_PER_FILE]
        if total + len(snippet) > _CTX_BUDGET:
            break
        parts.append(f"### ARQUIVO: {fp}\n```\n{snippet}\n```")
        total += len(snippet)
    return "\n\n".join(parts)


async def build_component_wiki(repo: Path, component: str, version: str, out_dir: Path, model: str | None = None, verify: bool = True) -> Path:
    credential = DefaultAzureCredential()

    def _agent(name: str, instructions: str):
        return FoundryChatClient(
            project_endpoint=settings.foundry_project_endpoint or None,
            model=model or settings.foundry_model,
            credential=credential,
        ).as_agent(name=name, instructions=instructions)

    files = gather_source(repo)
    if not files:
        raise SystemExit(f"No source files found under {repo}")
    tree = "\n".join(f"- {p} ({len(c)} chars)" for p, c in files.items())
    print(f"  read {len(files)} source files from {repo.name}", flush=True)

    # 1) Planner — one call: pick the pages + which files each needs.
    planner = _agent(
        "WikiPlanner",
        "Você é um arquiteto de documentação. Dado o componente e a lista de arquivos do "
        "repositório, planeje 5-8 páginas de wiki adaptadas ao stack real (ex.: Visão Geral, "
        "Arquitetura, API/Endpoints, Configuração, Integrações, Execução/Deploy). Para cada "
        "página, escolha os arquivos relevantes. Responda APENAS um JSON: "
        '{"pages":[{"title":"...","files":["caminho1","caminho2"]}]}',
    )
    async with planner:
        plan_raw = (await planner.run(
            f"Componente: {component} {version}\nArquivos do repositório:\n{tree}\n\nPlaneje as páginas."
        )).text
    plan = _parse_json(plan_raw).get("pages", [])
    if not plan:
        raise SystemExit(f"Planner returned no pages. Raw: {plan_raw[:300]}")
    print(f"  planned {len(plan)} pages", flush=True)

    # 2) Page writer — one call per page, paced, grounded in the assigned files.
    rules = _writer_rules()
    writer = _agent(
        "WikiPageWriter",
        "Você escreve UMA página de wiki técnica em pt-BR, **ancorada no código real fornecido**. "
        "Siga estas regras (skill wiki-page-writer da Microsoft):\n\n" + rules + "\n\n"
        "Adaptações: a fonte são os ARQUIVOS fornecidos no prompt (não use git/tools). Cite caminhos "
        "reais `(caminho)` e nomes de classes/funções. NÃO invente; se algo é incerto/ausente, diga. "
        "Saída: só o markdown da página (H2/H3), sem frontmatter VitePress.",
    )
    # Verifier — the fidelity step: re-grounds each page against the source, removing
    # or correcting any claim not explicitly supported (the wiki-page-writer "Validate").
    verifier = _agent(
        "WikiVerifier",
        "Você é um verificador de FIDELIDADE rigoroso. Dado os ARQUIVOS-FONTE e uma PÁGINA, "
        "reescreva a página removendo ou corrigindo TODA afirmação que NÃO tenha suporte explícito "
        "no código fornecido. Mantenha apenas o que é fato do fonte, com a citação do arquivo. "
        "Se uma seção inteira não tem suporte, remova-a. Não adicione informação nova. "
        "Saída: APENAS a página corrigida em markdown, nada mais.",
    )

    pages: list[dict] = []
    async with writer, verifier:
        for i, p in enumerate(plan, 1):
            ctx = _page_context(files, p.get("files", []))
            md = (await writer.run(
                f"Componente: {component} {version}\nPágina: {p['title']}\n\nFONTE:\n{ctx}\n\n"
                f"Escreva a página '{p['title']}'."
            )).text
            if verify:
                await asyncio.sleep(_PAGE_DELAY_S)
                md = (await verifier.run(
                    f"ARQUIVOS-FONTE:\n{ctx}\n\nPÁGINA:\n{md}\n\nCorrija para 100% ancorado no fonte."
                )).text
            pages.append({"title": p["title"], "content": md})
            print(f"  ✓ page {i}/{len(plan)}: {p['title']}" + (" (verificada)" if verify else ""), flush=True)
            if i < len(plan):
                await asyncio.sleep(_PAGE_DELAY_S)

    # 3) Assemble the bundle (the format ingest_cockpit consumes).
    bundle = out_dir / component / version
    (bundle / "pages").mkdir(parents=True, exist_ok=True)
    manifest_pages, llms = [], [f"# {component} {version}\n"]
    for order, page in enumerate(pages, 1):
        norm = f"page-{order}"
        (bundle / "pages" / f"{norm}.md").write_text(page["content"], encoding="utf-8")
        manifest_pages.append(
            {"id": norm, "title": page["title"], "order": order, "file": f"pages/{norm}.md", "audience": "base"}
        )
        llms.append(f"- [{page['title']}](pages/{norm}.md)")
    manifest = {
        "key": f"{component}-{version}", "title": f"{component} {version}",
        "source": {"type": "repo", "ref": str(repo), "commit": ""},
        "language": "pt-br", "model": settings.foundry_model,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "element", "component": component, "componentVersion": version,
        "releaseVersion": None, "pages": manifest_pages,
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (bundle / "llms.txt").write_text("\n".join(llms) + "\n", encoding="utf-8")
    print(f"\n✅ Bundle: {bundle}  ({len(manifest_pages)} páginas + manifest.json + llms.txt)", flush=True)
    return bundle


def _parse_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:  # strip code fences
        text = text.split("```")[1].lstrip("json").strip() if "```json" in text else text.split("```")[1].strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start : end + 1]) if start >= 0 else {}
    except json.JSONDecodeError:
        return {}


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser(description="Generate a faithful wiki bundle from a repo (Foundry).")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--component", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", default="/tmp/wiki-out")
    ap.add_argument("--model", default=None, help="Model deployment for the builder (default: FOUNDRY_MODEL)")
    ap.add_argument("--no-verify", action="store_true", help="Skip the fidelity verifier pass")
    args = ap.parse_args()
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    asyncio.run(build_component_wiki(repo, args.component, args.version, Path(args.out).expanduser(), args.model, verify=not args.no_verify))


if __name__ == "__main__":
    main()
