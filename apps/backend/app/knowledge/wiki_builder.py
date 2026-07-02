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
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.core.tenant import tenant_config

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent / "skills"
_IGNORE = {
    "node_modules", "bin", "obj", "packages", ".vs", "target", "vendor",
    ".terraform", "dist", "build", ".venv", "__pycache__", ".git", ".idea",
    # Frontend/tooling build output + azd env (compiled .js, caches — not source).
    ".next", ".turbo", "coverage", ".azure", ".pytest_cache", ".ruff_cache",
    # Skip git worktrees / agent scratch: they hold feature-branch copies of the
    # source and would make the wiki cite `.worktrees/<branch>/src/...` instead of
    # the canonical `src/...` — a fidelity defect for a source-grounded wiki.
    ".worktrees", ".worktree", ".auto-claude",
}
_SOURCE_EXT = {".cs", ".py", ".ts", ".tsx", ".js", ".go", ".java", ".json", ".yaml",
               ".yml", ".toml", ".md", ".csproj", ".sln", ".sql", ".sh", ".tf"}
_MAX_FILE_CHARS = 16_000
_PAGE_DELAY_S = 8  # pace page calls to stay under the model TPM cap


# --- Phase 1: deterministic fidelity gate -------------------------------------
# A source-grounded wiki must cite REAL files. After the verifier pass we measure what
# fraction of the wiki's file citations actually resolve to a file in the gathered
# source (and that none point into a git worktree), and gate the bundle on it. This
# turns "the KB is built faithfully" into a number, not a vibe (Phase 1 of the plan).
# Longest extension FIRST in the alternation: regex alternation is first-match, so an
# alphabetical sort would match `.js` inside `main.parameters.json` (js < json) and the
# truncated `main.parameters.js` never resolves — silently failing every .json/.tsx
# citation. (Found by dogfooding this gate on our own infra/frontend, which are
# .json/.tsx-heavy; the Python-heavy backend hid it.) Sort by length desc, then alpha.
_EXT_ALT = "|".join(sorted((e.lstrip(".") for e in _SOURCE_EXT), key=lambda e: (-len(e), e)))
_CITE_RE = re.compile(rf"((?:[\w.-]+/)*[\w.-]+\.(?:{_EXT_ALT}))(?::\d+(?:-\d+)?)?")
# The two generation paths cite differently: the Foundry pipeline emits repo-relative paths,
# but the deep-wiki Agent Skill (VS Code Copilot / Claude Code) resolves the git remote and
# cites full GitHub blob URLs (…/blob/<ref>/infra/resources.bicep). Strip the blob-URL prefix
# so both reduce to the same repo-relative path the resolver matches — the gate scores either
# path. (Found by actually running the Copilot CLI path: 100% faithful, but scored ~44% until
# the URL form was normalized.)
_BLOB_URL_RE = re.compile(r"(?:https?:)?//github\.com/[^/\s]+/[^/\s]+/blob/[^/\s]+/")
# After reducing blob URLs to repo paths, drop any REMAINING external URLs (schema refs like
# schema.management.azure.com/…/deploymentParameters.json, doc links): the fidelity gate
# measures FILE-PATH citations, not external URLs — counting those as failed citations
# under-scores a faithful page.
_URL_RE = re.compile(r"https?://\S+")


def _fidelity_report(pages: list[dict], files: dict[str, str]) -> dict:
    """Resolve every file citation in the pages against the real source.

    A citation resolves if its path equals, or is a path-suffix of, a real source file
    (citations are often relative/partial). Citations into `.worktrees` are defects.
    score = resolved / total; 0 if a faithful wiki cited nothing at all."""
    keys = set(files)
    basenames: dict[str, int] = {}
    for k in keys:
        basenames[k.rsplit("/", 1)[-1]] = basenames.get(k.rsplit("/", 1)[-1], 0) + 1

    total = resolved = line_ranged = worktree = 0
    distinct: set[str] = set()
    for page in pages:
        text = _BLOB_URL_RE.sub("", page.get("content", ""))  # GitHub blob URL → repo-relative path
        text = _URL_RE.sub("", text)  # drop remaining external URLs (not file citations)
        for m in _CITE_RE.finditer(text):
            cited = m.group(1).lstrip("./")
            total += 1
            if ":" in m.group(0):
                line_ranged += 1
            if "worktree" in cited:  # note: leading "." already stripped above
                worktree += 1
                continue
            hit = (
                cited in keys
                or any(k.endswith("/" + cited) for k in keys)
                or ("/" not in cited and basenames.get(cited, 0) == 1)
            )
            if hit:
                resolved += 1
                distinct.add(cited)
    score = (resolved / total) if total else 0.0
    return {
        "total": total, "resolved": resolved, "line_ranged": line_ranged,
        "worktree": worktree, "distinct": len(distinct), "score": score,
    }


def _fidelity_floor() -> float:
    """Read build.fidelity_min from the single source of truth (eval/assurance.yaml)."""
    try:
        import yaml

        cfg = yaml.safe_load(
            (Path(__file__).resolve().parents[2] / "eval" / "assurance.yaml").read_text(encoding="utf-8")
        )
        return float(((cfg or {}).get("build") or {}).get("fidelity_min", 0.80))
    except Exception:  # noqa: BLE001 — gate falls back to a sane default if config is absent
        return 0.80


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


# ── Cost instrumentation (Microsoft pattern) ─────────────────────────────────
# The agent-framework already emits OpenTelemetry **GenAI semantic-convention**
# spans on every model call (gen_ai.usage.input_tokens / output_tokens). Two
# complementary layers, both reading that same usage:
#   A) Platform — when APPLICATIONINSIGHTS_CONNECTION_STRING is set we light up the
#      standard export (configure_azure_monitor + enable_instrumentation) so tokens
#      land in the Foundry *Tracing* / App Insights "Agents" view. Off → zero infra.
#   B) Cost report — we read response.raw_representation.usage_details per call and
#      print a run-scoped tokens+R$ rollup (the money number dashboards don't compute).

# USD per 1M tokens (input, output). TOKENS are measured exactly; these PRICES are
# editable estimates (Azure/OpenAI list, 2026) — confirm against your billing.
_PRICE_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5-codex":  (1.25, 10.00),
    "gpt-5-mini":   (0.25,  2.00),
    "gpt-5":        (1.25, 10.00),
    "gpt-4.1-mini": (0.40,  1.60),
    "gpt-4.1":      (2.00,  8.00),
}
_DEFAULT_PRICE = (1.25, 10.00)  # conservative fallback for unknown deployments
_USD_BRL = float(os.environ.get("USD_BRL", "5.40"))


def _price_for(model: str) -> tuple[float, float]:
    m = model.lower()
    for key, price in _PRICE_USD_PER_1M.items():
        if m.startswith(key):
            return price
    return _DEFAULT_PRICE


def _usage(response) -> tuple[int, int]:
    """(input, output) tokens from a response's gen_ai usage details."""
    raw = getattr(response, "raw_representation", None)
    u = getattr(raw, "usage_details", None) or {}
    return int(u.get("input_token_count", 0) or 0), int(u.get("output_token_count", 0) or 0)


class _CostMeter:
    """Run-scoped token + cost rollup, fed one agent response at a time."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.input = self.output = self.calls = 0

    def add(self, response) -> None:
        i, o = _usage(response)
        self.input += i
        self.output += o
        self.calls += 1

    def report(self) -> str:
        pin, pout = _price_for(self.model)
        usd = self.input / 1e6 * pin + self.output / 1e6 * pout
        return (
            f"💰 Custo ({self.model}, {self.calls} chamadas): "
            f"{self.input / 1000:.1f}K in + {self.output / 1000:.1f}K out "
            f"= ${usd:.2f} (~R${usd * _USD_BRL:.2f})  "
            f"[preço {pin}/{pout} USD/1M · USD_BRL={_USD_BRL} — configurável]"
        )


def _maybe_setup_observability() -> bool:
    """Microsoft pattern: export the gen_ai OTEL spans to Application Insights.
    Uses APPLICATIONINSIGHTS_CONNECTION_STRING when set, else the convenience path —
    fetch it from the Foundry project (telemetry.get_application_insights_connection_string).
    No-op (returns False) when neither yields a connection — zero infra, no error."""
    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        try:
            from azure.ai.projects import AIProjectClient
            project = AIProjectClient(
                endpoint=tenant_config().foundry_project_endpoint, credential=DefaultAzureCredential()
            )
            conn = project.telemetry.get_application_insights_connection_string()
        except Exception:
            conn = None
    if not conn:
        return False
    try:
        from agent_framework.observability import enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        print("  (observability: azure-monitor-opentelemetry não instalado — `uv add azure-monitor-opentelemetry`)", flush=True)
        return False
    configure_azure_monitor(connection_string=conn)
    enable_instrumentation()
    print("  observability: spans gen_ai → Application Insights (Foundry Tracing / Agents view)", flush=True)
    return True


# Transient conditions a freshly-provisioned (or rate-limited) Foundry project throws:
# the inference routing for a just-created project propagates for ~10-20 min, so bursts
# of calls intermittently 404 with "Project not found" even though isolated calls work;
# a small deployment also 429s under the page loop. Retry both with backoff — isolated
# retries land on warmed nodes, so spreading them out converges.
_TRANSIENT_MARKERS = (
    "project not found", "not found", "429", "rate limit", "rate_limit",
    "timeout", "timed out", "502", "503", "temporarily unavailable", "service unavailable",
)


async def _run_resilient(agent, prompt: str, *, label: str, retries: int = 7, base_delay: int = 10):
    """Run one agent turn, retrying on transient Foundry conditions with exponential backoff."""
    delay = base_delay
    for attempt in range(retries):
        try:
            return await agent.run(prompt)
        except Exception as exc:  # noqa: BLE001
            s = str(exc).lower()
            if attempt < retries - 1 and any(m in s for m in _TRANSIENT_MARKERS):
                print(f"  ⏳ {label}: transient ({s[:60]}…); retry {attempt + 1}/{retries - 1} in {delay}s", flush=True)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 90)
                continue
            raise


async def build_component_wiki(repo: Path, component: str, version: str, out_dir: Path, model: str | None = None, verify: bool = True, groups: list[str] | None = None, fidelity_root: Path | None = None) -> Path:
    credential = DefaultAzureCredential()
    resolved_model = model or tenant_config().foundry_model
    meter = _CostMeter(resolved_model)
    _maybe_setup_observability()

    def _agent(name: str, instructions: str):
        return FoundryChatClient(
            project_endpoint=tenant_config().foundry_project_endpoint or None,
            model=model or tenant_config().foundry_model,
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
        plan_resp = await _run_resilient(
            planner,
            f"Componente: {component} {version}\nArquivos do repositório:\n{tree}\n\nPlaneje as páginas.",
            label="planner",
        )
    meter.add(plan_resp)
    plan_raw = plan_resp.text
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
            w_resp = await _run_resilient(
                writer,
                f"Componente: {component} {version}\nPágina: {p['title']}\n\nFONTE:\n{ctx}\n\n"
                f"Escreva a página '{p['title']}'.",
                label=f"writer p{i}",
            )
            meter.add(w_resp)
            md = w_resp.text
            if verify:
                await asyncio.sleep(_PAGE_DELAY_S)
                v_resp = await _run_resilient(
                    verifier,
                    f"ARQUIVOS-FONTE:\n{ctx}\n\nPÁGINA:\n{md}\n\nCorrija para 100% ancorado no fonte.",
                    label=f"verifier p{i}",
                )
                meter.add(v_resp)
                md = v_resp.text
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
        "language": "pt-br", "model": resolved_model,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "element", "component": component, "componentVersion": version,
        "releaseVersion": None, "pages": manifest_pages,
        # Access inherited from the source repo (its read teams) — the ingest stamps
        # these as the document's allowed groups. Empty = the owner declares access
        # elsewhere (external map) or it's fail-closed. NOT a classification guess.
        "groups": groups or [],
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (bundle / "llms.txt").write_text("\n".join(llms) + "\n", encoding="utf-8")
    print(f"\n✅ Bundle: {bundle}  ({len(manifest_pages)} páginas + manifest.json + llms.txt)", flush=True)
    print(meter.report(), flush=True)

    # Fidelity gate (Phase 1) — the bundle is written above for inspection, but a wiki
    # whose citations don't resolve to real source (or cite a worktree) must not reach
    # the KB. Gates only when the verifier ran (the fidelity claim depends on it).
    # A monorepo sub-area bundle (e.g. --repo docs) legitimately cites files in OTHER
    # areas (apps/, infra/). Resolve citations against the wider root when given, so the
    # gate doesn't penalize honest cross-area references. Defaults to the --repo gather.
    fidelity_files = gather_source(fidelity_root) if fidelity_root else files
    fid = _fidelity_report(pages, fidelity_files)
    print(
        f"\nFidelity: {fid['score']:.0%} — {fid['resolved']}/{fid['total']} citações resolvem para "
        f"arquivo real | {fid['distinct']} arquivos distintos, {fid['line_ranged']} com linha, "
        f"{fid['worktree']} em worktree",
        flush=True,
    )
    floor = _fidelity_floor()
    if verify and (fid["score"] + 1e-9 < floor or fid["worktree"] > 0):
        print(
            f"❌ Fidelity gate FAILED (< {floor:.0%} ou citações em worktree) — "
            "bundle escrito para inspeção, NÃO ingerir.",
            flush=True,
        )
        raise SystemExit(1)
    if verify:
        print(f"✅ Fidelity gate PASSED (≥ {floor:.0%}).", flush=True)
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
    ap.add_argument("--groups", default="", help="Comma-separated read groups of the source repo (inherited access; written to the manifest)")
    ap.add_argument("--fidelity-root", default=None, help="Resolve fidelity citations against THIS dir instead of --repo (use the monorepo root for a sub-area bundle that cites other areas, e.g. docs/ citing apps/)")
    args = ap.parse_args()
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"repo not found: {repo}")
    fidelity_root = Path(args.fidelity_root).expanduser().resolve() if args.fidelity_root else None
    if fidelity_root and not fidelity_root.is_dir():
        raise SystemExit(f"--fidelity-root not found: {fidelity_root}")
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    asyncio.run(build_component_wiki(repo, args.component, args.version, Path(args.out).expanduser(), args.model, verify=not args.no_verify, groups=groups, fidelity_root=fidelity_root))


if __name__ == "__main__":
    main()
