"""Set up continuous (online) evaluation on the deployed hosted agent.

Creates an EvaluationRule so Foundry scores the agent's LIVE responses (on every
RESPONSE_COMPLETED) against an existing eval — the continuous-improvement loop: each
interaction is scored and the scores link back to its trace in the Foundry Control
Plane, instead of only the offline golden-set run (eval/run_eval.py).

Prerequisite: an eval definition to run, by id. The quickest source is a cloud
eval run from our offline harness — `uv run python -m eval.run_eval --cloud` prints
a portal URL containing `eval_<id>`; pass that as --eval-id.

  uv run python -m app.eval_rule_provision --eval-id eval_xxxxxxxx [--max-hourly 10]
  uv run python -m app.eval_rule_provision --delete            # remove the rule

Run after `azd deploy helpdesk-concierge`. APIs verified against azure-ai-projects
2.2.0 (evaluation_rules.create_or_update/delete, EvaluationRule, EvaluationRuleFilter,
ContinuousEvaluationRuleAction, EvaluationRuleEventType).
"""

from __future__ import annotations

import argparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    ContinuousEvaluationRuleAction,
    EvaluationRule,
    EvaluationRuleEventType,
    EvaluationRuleFilter,
)
from azure.identity import DefaultAzureCredential

from app.core.settings import settings
from app.core.tenant import tenant_config

_RULE_ID = "helpdesk-online-eval"


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuous evaluation rule for the hosted agent.")
    parser.add_argument("--eval-id", help="id of the eval to run on live traces (e.g. eval_xxx from a --cloud run's report_url)")
    parser.add_argument("--max-hourly", type=int, default=10, help="cap on eval runs per hour")
    parser.add_argument("--rule-id", default=_RULE_ID, help="evaluation rule id")
    parser.add_argument("--delete", action="store_true", help="delete the rule instead of creating it")
    args = parser.parse_args()

    project = AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )

    if args.delete:
        project.evaluation_rules.delete(id=args.rule_id)
        print(f"🗑️  Deleted continuous eval rule '{args.rule_id}'.")
        return

    if not args.eval_id:
        parser.error("--eval-id is required (or use --delete)")

    rule = EvaluationRule(
        display_name="Helpdesk online evaluation",
        description="Scores each hosted-agent response against the eval, continuously.",
        event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
        filter=EvaluationRuleFilter(agent_name=tenant_config().hosted_agent_name),
        action=ContinuousEvaluationRuleAction(eval_id=args.eval_id, max_hourly_runs=args.max_hourly),
        enabled=True,
    )
    project.evaluation_rules.create_or_update(id=args.rule_id, evaluation_rule=rule)
    print(
        f"✅ Continuous eval rule '{args.rule_id}' created — scoring every response from "
        f"'{tenant_config().hosted_agent_name}' against eval {args.eval_id} (≤{args.max_hourly}/h)."
    )


if __name__ == "__main__":
    main()
