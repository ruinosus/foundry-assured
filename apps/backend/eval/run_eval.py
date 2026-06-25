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

from app.agents.concierge import build_concierge_agent
from app.core.settings import settings
from eval.assertions import (
    _TITLE_PREFIX,
    check_cites_a_source,
    check_no_secret_leaked,
    cites_a_source,
    no_secret_leaked,
    secret_findings,
)

_DATASETS = Path(__file__).resolve().parent / "datasets"
_GOLDEN = _DATASETS / "golden.jsonl"
_ADVERSARIAL = _DATASETS / "adversarial.jsonl"
_CORPUS = Path(__file__).resolve().parent.parent / "app" / "knowledge" / "corpus"
_RUNS = Path(__file__).resolve().parent / "runs.jsonl"


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


async def _build_items(agent, rows: list[dict]) -> list[EvalItem]:
    """Run the agent on each query and wrap the turn (with its source runbook as
    grounding context) into an EvalItem.

    Adversarial prompts often get stopped by Azure's content/jailbreak filter
    *before* the model — that's a safe outcome, so we treat the resulting error as
    a refusal rather than letting it crash the run."""
    corpus = _corpus_by_title()
    items: list[EvalItem] = []
    blocked = 0
    for row in rows:
        query = row["query"]
        try:
            response = await agent.run(query)
            text = response.text or ""
        except Exception as exc:  # noqa: BLE001 — classify content-filter blocks
            if any(marker in str(exc).lower() for marker in _FILTER_MARKERS):
                text = _BLOCKED_ANSWER
                blocked += 1
            else:
                raise
        context = corpus.get((row.get("source") or "").lower(), "")
        items.append(
            EvalItem(
                conversation=[Message("user", [query]), Message("assistant", [text])],
                context=context or None,
                expected_output=row.get("expected_output") or None,
            )
        )
    if blocked:
        print(f"🛡️  {blocked}/{len(rows)} prompt(s) blocked upfront by the Azure content/jailbreak filter.")
    return items


async def _run(cloud: bool, safety: bool) -> int:
    # --safety swaps the golden set for adversarial/jailbreak prompts and the
    # Foundry quality judges for safety judges. The same local gate applies: the
    # answer must decline or stay grounded (cites_a_source passes refusals) and
    # never leak a secret — i.e. it didn't get jailbroken off-policy.
    rows = _load_dataset(_ADVERSARIAL if safety else _GOLDEN)
    eval_name = "helpdesk-safety" if safety else "helpdesk-golden"
    local = LocalEvaluator(cites_a_source, no_secret_leaked)

    cred = project = foundry = None
    if cloud:
        from agent_framework.foundry import FoundryEvals
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        cred = DefaultAzureCredential()
        project = AIProjectClient(
            endpoint=settings.foundry_project_endpoint, credential=cred
        )
        quality = [FoundryEvals.GROUNDEDNESS, FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE]
        harms = [
            FoundryEvals.VIOLENCE,
            FoundryEvals.SELF_HARM,
            FoundryEvals.SEXUAL,
            FoundryEvals.HATE_UNFAIRNESS,
        ]
        foundry = FoundryEvals(
            project_client=project,
            model=settings.foundry_model,
            evaluators=harms if safety else quality,
        )

    judges = "Foundry safety judges" if safety else "Foundry cloud judges"
    where = "local policy gate" + (f" + {judges}" if cloud else "")
    print(f"Evaluating {len(rows)} {'adversarial' if safety else 'golden'} queries with: {where}")

    try:
        # `async with` closes the agent's chat-client session cleanly.
        async with build_concierge_agent() as agent:
            items = await _build_items(agent, rows)

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

    # The LOCAL policy result is the hard gate; Foundry scores are graded signal,
    # not a blocker, so a flaky judge score can't break CI.
    gate_failed = False
    try:
        results[0].raise_for_status()
        ok = (
            "every answer refused or stayed grounded, and leaked no secret."
            if safety
            else "every answer cited a source and leaked no secret."
        )
        print(f"\n✅ Policy gate PASSED — {ok}")
    except EvalNotPassedError as exc:
        gate_failed = True
        print(f"\n❌ Policy gate FAILED — {exc}")

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
    parser = argparse.ArgumentParser(description="Helpdesk eval harness (Phase 5).")
    parser.add_argument("--cloud", action="store_true", help="add Foundry cloud evaluators (groundedness/relevance/coherence, or safety judges with --safety)")
    parser.add_argument("--safety", action="store_true", help="run the adversarial/jailbreak set; gate on refuse-or-ground + no-secret, score with Foundry safety judges")
    parser.add_argument("--self-test", action="store_true", help="prove the policy gate catches a planted violation (no network)")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(_self_test())
    sys.exit(asyncio.run(_run(cloud=args.cloud, safety=args.safety)))


if __name__ == "__main__":
    main()
