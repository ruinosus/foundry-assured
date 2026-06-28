"""Offline eval harness for the Helpdesk Concierge (Phase 5).

Runs the grounded concierge agent against the golden set and scores it with two
layers, using the agent-framework evaluation API exactly as intended:

  * LocalEvaluator (eval/assertions.py) — deterministic policy gate: every answer
    must cite a runbook source (or decline) and must never leak a secret. This is
    the CI gate — a violation makes the run exit non-zero.
  * FoundryEvals (--cloud) — Microsoft Foundry's hosted LLM-judge evaluators
    (groundedness / relevance / coherence). Scores are viewable in the Foundry
    portal (report_url), tying eval back to traces.

Usage (from backend/):
    uv run python -m eval.run_eval              # local policy gate (fast)
    uv run python -m eval.run_eval --cloud      # + Foundry cloud scores
    uv run python -m eval.run_eval --self-test  # prove the gate catches a planted violation

API note (CLAUDE.md rule #1): signatures verified against the INSTALLED
agent-framework 1.9.0. The public docs show drift — the installed FoundryEvals
takes `model=` (not `model_deployment=`) and EvalResults gates via
`raise_for_status()` (not the doc's `assert_passed()`).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_framework import EvalItem, EvalNotPassedError, LocalEvaluator, Message

from app.agents.cockpit import build_cockpit_agent
from app.agents.concierge import build_concierge_agent
from app.agents.selfwiki import build_selfwiki_agent
from app.core.settings import settings
from eval.assertions import (
    _TITLE_PREFIX,
    check_cites_a_source,
    check_no_secret_leaked,
    cites_a_source,
    cockpit_cites_source,
    no_secret_leaked,
    secret_findings,
    selfwiki_cites_source,
)

_DATASETS = Path(__file__).resolve().parent / "datasets"
_GOLDEN = _DATASETS / "golden.jsonl"
_COCKPIT_GOLDEN = _DATASETS / "cockpit_golden.jsonl"
_SELFWIKI_GOLDEN = _DATASETS / "selfwiki_golden.jsonl"
_ADVERSARIAL = _DATASETS / "adversarial.jsonl"
_CORPUS = Path(__file__).resolve().parent.parent / "app" / "knowledge" / "corpus"
_RUNS = Path(__file__).resolve().parent / "runs.jsonl"
_ASSURANCE = Path(__file__).resolve().parent / "assurance.yaml"


def _load_assurance() -> dict:
    """The measured-guarantee thresholds (Phase 0). Single source of truth the gates read."""
    try:
        import yaml

        return yaml.safe_load(_ASSURANCE.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, ImportError):
        return {}


def _completeness_gate(
    rows: list[dict], items: list, threshold: float
) -> tuple[bool, str | None]:
    """Deterministic completeness gate (Phase 3).

    Golden rows that carry an ``expected_set`` — a *source-verified* list of items the
    answer must mention (e.g. every MCP server) — are scored by coverage: the fraction
    of the set the answer names. The mean coverage across those rows must meet
    ``threshold``. Deterministic (no LLM judge) so it can hard-gate CI, and it targets
    the exact failure the agent showed (listing 6 of 9 MCP servers). Rows without an
    ``expected_set`` are skipped (their correctness is judged elsewhere)."""
    scored: list[tuple[str, int, int, list[str]]] = []
    for row, item in zip(rows, items):
        expected = row.get("expected_set") or []
        if not expected:
            continue
        answer = (item.conversation[-1].text or "").lower()
        missing = [e for e in expected if str(e).lower() not in answer]
        scored.append(
            (row.get("query", "")[:48], len(expected) - len(missing), len(expected), missing)
        )
    if not scored:
        return True, None
    mean = sum(hit / total for _, hit, total, _ in scored) / len(scored)
    lines = [
        f"   {hit}/{total}  {q}" + (f"  ✗ faltou: {', '.join(miss)}" if miss else "  ✓")
        for q, hit, total, miss in scored
    ]
    summary = (
        f"Completeness: cobertura média {mean:.0%} (threshold {threshold:.0%}) "
        f"em {len(scored)} pergunta(s) de enumeração\n" + "\n".join(lines)
    )
    return mean + 1e-9 >= threshold, summary


def _load_dataset(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _corpus_by_title() -> dict[str, str]:
    """Map each runbook's H1 title (prefix-stripped, lowercased) to its full text.

    The golden set's ``source`` field names the runbook a query should be grounded
    in; we feed that runbook's text as the EvalItem ``context`` so Foundry's
    groundedness judge has something to check the answer against.
    """
    by_title: dict[str, str] = {}
    for md in sorted(_CORPUS.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("# "):
                title = _TITLE_PREFIX.sub("", line[2:].strip()).lower()
                by_title[title] = text
                break
    return by_title


def _print_results(r) -> None:
    print(f"\n[{r.provider}]  passed {r.passed}/{r.total}  failed {r.failed}")
    if getattr(r, "report_url", None):
        print(f"  portal: {r.report_url}")
    for check, counts in (r.per_evaluator or {}).items():
        print(f"    {check}: {counts}")
    for item in r.items or []:
        # Per-item pass/fail lives in the scores, not item.status (which is the run
        # status, e.g. "completed"). Only `passed is False` is a real failure — a
        # None means the dimension didn't score that item (e.g. groundedness with
        # no surfaced context), which we skip rather than report as a failure.
        failed = [s.name for s in (item.scores or []) if s.passed is False]
        if failed:
            snippet = (item.output_text or "").replace("\n", " ")[:90]
            why = item.error_message or ", ".join(failed)
            print(f"    FAIL [{item.item_id}] {why} «{snippet}»")


_FILTER_MARKERS = ("content_filter", "contentfiltered", "jailbreak", "content management policy")
_BLOCKED_ANSWER = "I can't help with that — the request was blocked by the content safety filter."


# Transient conditions to retry: rate limits AND the "Project not found" 404 a
# freshly-(re)provisioned Foundry project intermittently throws under burst while its
# inference routing propagates (and connection resets). Same class the wiki_builder
# retries — without it, one flaky call crashes the whole eval run.
_TRANSIENT_MARKERS = (
    "429", "rate limit", "rate_limit", "project not found", "not found",
    "timeout", "timed out", "502", "503", "temporarily unavailable",
    "service unavailable", "connection aborted", "remotedisconnected",
)


async def _agent_answer(agent, query: str, *, retries: int = 6) -> str:
    """Run one query, retrying on transient Foundry conditions. The agent does agentic
    retrieval (several model calls per query), so a tight loop bursts over the deployment
    TPM cap — and a just-provisioned project intermittently 404s — so back off and retry
    instead of failing the whole run. Content-filter blocks are re-raised for the caller
    to classify as a refusal."""
    delay = 15
    for attempt in range(retries):
        try:
            return (await agent.run(query)).text or ""
        except Exception as exc:  # noqa: BLE001
            s = str(exc).lower()
            if any(marker in s for marker in _FILTER_MARKERS):
                raise
            transient = any(marker in s for marker in _TRANSIENT_MARKERS)
            if transient and attempt < retries - 1:
                print(f"  ⏳ transient ({s[:50]}…); retry in {delay}s…", flush=True)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 90)
                continue
            raise


async def _build_items(
    agent, rows: list[dict], *, use_context: bool = True,
    expected_field: str = "expected_output", pace_s: float = 0.0,
) -> list[EvalItem]:
    """Run the agent on each query and wrap the turn into an EvalItem.

    Helpdesk feeds the named runbook's text as grounding ``context`` (groundedness).
    Cockpit grounds in a cloud KB with no local source file, so it carries no context
    and instead supplies the golden ``expected`` answer for reference-based judges
    (similarity / response completeness).

    Adversarial prompts often get stopped by Azure's content/jailbreak filter
    *before* the model — that's a safe outcome, so we treat the resulting error as
    a refusal rather than letting it crash the run."""
    corpus = _corpus_by_title() if use_context else {}
    items: list[EvalItem] = []
    blocked = 0
    for i, row in enumerate(rows):
        query = row["query"]
        try:
            text = await _agent_answer(agent, query)
        except Exception as exc:  # noqa: BLE001 — classify content-filter blocks
            if any(marker in str(exc).lower() for marker in _FILTER_MARKERS):
                text = _BLOCKED_ANSWER
                blocked += 1
            else:
                raise
        context = corpus.get((row.get("source") or "").lower(), "") if use_context else ""
        items.append(
            EvalItem(
                conversation=[Message("user", [query]), Message("assistant", [text])],
                context=context or None,
                expected_output=row.get(expected_field) or None,
            )
        )
        if pace_s and i < len(rows) - 1:
            await asyncio.sleep(pace_s)
    if blocked:
        print(f"🛡️  {blocked}/{len(rows)} prompt(s) blocked upfront by the Azure content/jailbreak filter.")
    return items


async def _run(cloud: bool, safety: bool, domain: str) -> int:
    # Domain config. helpdesk: grounded against local runbooks (+ --safety swaps in
    # the adversarial set and safety judges). cockpit: a second domain grounded in a
    # cloud Foundry IQ KB (no local source file), measured for *correctness* against
    # the golden `expected` answer (reference-based judges), not groundedness.
    if domain == "cockpit":
        rows = _load_dataset(_COCKPIT_GOLDEN)
        eval_name = "cockpit-golden"
        local = LocalEvaluator(cockpit_cites_source, no_secret_leaked)
        agent_factory = build_cockpit_agent
        build_kwargs = {"use_context": False, "expected_field": "expected", "pace_s": 3.0}
        label = "cockpit golden"
    elif domain == "selfwiki":
        # Third domain (dogfood): grounded in a deep-wiki generated from THIS repo.
        # Like cockpit, the corpus is a cloud Foundry IQ KB (no local source file), so
        # we score correctness against the golden `expected` (reference-based judges),
        # not groundedness, and gate locally on a citation/decline floor.
        rows = _load_dataset(_SELFWIKI_GOLDEN)
        eval_name = "selfwiki-golden"
        local = LocalEvaluator(selfwiki_cites_source, no_secret_leaked)
        agent_factory = build_selfwiki_agent
        build_kwargs = {"use_context": False, "expected_field": "expected", "pace_s": 3.0}
        label = "selfwiki golden"
    else:
        rows = _load_dataset(_ADVERSARIAL if safety else _GOLDEN)
        eval_name = "helpdesk-safety" if safety else "helpdesk-golden"
        local = LocalEvaluator(cites_a_source, no_secret_leaked)
        agent_factory = build_concierge_agent
        build_kwargs = {"use_context": True, "expected_field": "expected_output"}
        label = "adversarial" if safety else "golden"

    cred = project = foundry = None
    if cloud:
        from agent_framework.foundry import FoundryEvals
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        cred = DefaultAzureCredential()
        project = AIProjectClient(
            endpoint=settings.foundry_project_endpoint, credential=cred
        )
        if domain in ("cockpit", "selfwiki"):
            # SIMILARITY is the reference-based correctness score (answer vs the
            # golden `expected`) — the cloud analogue of the source-verified
            # "key-fact" judge — plus relevance/coherence. (RESPONSE_COMPLETENESS is
            # omitted: it requires an explicit `ground_truth` data mapping the simple
            # EvalItem path doesn't supply.)
            evaluators = [
                FoundryEvals.SIMILARITY,
                FoundryEvals.RELEVANCE,
                FoundryEvals.COHERENCE,
            ]
        elif safety:
            evaluators = [
                FoundryEvals.VIOLENCE,
                FoundryEvals.SELF_HARM,
                FoundryEvals.SEXUAL,
                FoundryEvals.HATE_UNFAIRNESS,
            ]
        else:
            evaluators = [FoundryEvals.GROUNDEDNESS, FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE]
        foundry = FoundryEvals(
            project_client=project, model=settings.foundry_model, evaluators=evaluators
        )

    where = "local policy gate" + (" + Foundry cloud judges" if cloud else "")
    print(f"Evaluating {len(rows)} {label} queries [{domain}] with: {where}")

    try:
        # `async with` closes the agent's chat-client session cleanly.
        async with agent_factory() as agent:
            items = await _build_items(agent, rows, **build_kwargs)

        results = [await local.evaluate(items, eval_name=eval_name)]
        if foundry is not None:
            results.append(await foundry.evaluate(items, eval_name=eval_name))
    finally:
        if project is not None:
            await project.close()
        if cred is not None:
            await cred.close()

    for r in results:
        _print_results(r)

    # The LOCAL policy result + the completeness gate are the HARD gates (deterministic,
    # CI-blocking). Foundry cloud scores are graded signal, not a blocker, so a flaky
    # judge score can't break CI.
    gate_failed = False
    try:
        results[0].raise_for_status()
        print(f"\n✅ Policy gate PASSED — {eval_name}: every answer cited a source (or declined) and leaked no secret.")
    except EvalNotPassedError as exc:
        gate_failed = True
        print(f"\n❌ Policy gate FAILED — {exc}")

    # Completeness gate (Phase 3) — only bites on golden rows carrying an expected_set.
    completeness_min = (_load_assurance().get("quality") or {}).get("answer_completeness_min", 0.8)
    ok, summary = _completeness_gate(rows, items, completeness_min)
    if summary:
        print("\n" + summary)
        if ok:
            print(f"✅ Completeness gate PASSED (≥ {completeness_min:.0%}).")
        else:
            gate_failed = True
            print(f"❌ Completeness gate FAILED (< {completeness_min:.0%}).")

    _persist_run(results, len(rows), eval_name, cloud=cloud, gate_passed=not gate_failed)
    return 1 if gate_failed else 0


def _persist_run(
    results, num_queries: int, eval_name: str, *, cloud: bool, gate_passed: bool
) -> None:
    """Append a compact summary of this run to runs.jsonl for the /evals page."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_name": eval_name,
        "queries": num_queries,
        "cloud": cloud,
        "gate_passed": gate_passed,
        "providers": [
            {
                "provider": r.provider,
                "passed": r.passed,
                "total": r.total,
                "failed": r.failed,
                "report_url": getattr(r, "report_url", None),
                "checks": r.per_evaluator or {},
            }
            for r in results
        ],
    }
    with _RUNS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"📒 Run recorded to {_RUNS.name} ({len(results)} provider(s)).")


def _self_test() -> int:
    """Plant violations and prove the policies catch them (deterministic, offline)."""
    print("Self-test — feeding the policies deliberately bad answers:\n")
    no_cite = "Just restart your machine and it'll be fine."
    leaks = "Connect with AWS key AKIAIOSFODNN7EXAMPLE and you're set."

    cite_caught = not check_cites_a_source(no_cite)
    secret_caught = not check_no_secret_leaked(leaks)

    print(f"  cites_a_source  on no-citation answer  -> {'CAUGHT ✅' if cite_caught else 'missed ❌'}")
    print(f"      «{no_cite}»")
    print(f"  no_secret_leaked on credential answer  -> "
          f"{'CAUGHT ✅' if secret_caught else 'missed ❌'}  {secret_findings(leaks)}")
    print(f"      «{leaks}»")

    if cite_caught and secret_caught:
        print("\n✅ Gate bites: both planted violations were caught.")
        return 0
    print("\n❌ Gate did NOT catch a planted violation.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval harness (Phase 5) — helpdesk + cockpit domains.")
    parser.add_argument("--domain", choices=["helpdesk", "cockpit", "selfwiki"], default="helpdesk", help="which agent/golden to evaluate (default: helpdesk)")
    parser.add_argument("--cloud", action="store_true", help="add Foundry cloud evaluators (helpdesk: groundedness/relevance/coherence; cockpit: similarity/completeness/relevance/coherence; +safety judges with --safety)")
    parser.add_argument("--safety", action="store_true", help="[helpdesk] run the adversarial/jailbreak set; gate on refuse-or-ground + no-secret, score with Foundry safety judges")
    parser.add_argument("--self-test", action="store_true", help="prove the policy gate catches a planted violation (no network)")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(_self_test())
    if args.safety and args.domain != "helpdesk":
        parser.error("--safety applies to the helpdesk domain only")
    sys.exit(asyncio.run(_run(cloud=args.cloud, safety=args.safety, domain=args.domain)))


if __name__ == "__main__":
    main()
