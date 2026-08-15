---
type: backend-evals-and-tickets
title: Evaluations and tickets
description: Backend support for persisted tickets, local and Foundry-backed evaluation APIs, and the runtime surfaces that expose assurance results to users.
tags: [backend, evals, tickets, assurance]
---

# Evaluations and tickets

Two smaller but important backend subsystems support user-visible operations and assurance visibility:

- **tickets**, which persist escalation outcomes and expose them to the UI,
- **evaluation APIs**, which expose both local harness output and live Foundry evaluation runs.

These systems are operationally important because they connect runtime behavior back to visible audit trails.

## Ticket subsystem

The ticket implementation lives in [`apps/backend/app/tools/tickets.py`](../../apps/backend/app/tools/tickets.py).

### Core functions

- `create_ticket(summary: str, severity: str = "medium") -> dict`
- `list_tickets(limit: int = 50) -> list[dict]`
- `create_ticket_tool = tool(create_ticket, ...)`

### Persistence model

Tickets are stored in:

- `apps/backend/data/tickets.jsonl`

`create_ticket()`:

- generates a short ID like `HD-XXXXXX`,
- normalizes summary and severity,
- stamps an ISO timestamp,
- appends the JSON row to the JSONL file.

`list_tickets()` reads the file back, reverses rows to newest-first order, and applies a limit.

### Who uses it

- the live helpdesk workflow calls `create_ticket()` directly after approval and RBAC checks,
- the hosted/autonomous path can use `create_ticket_tool` as a model-callable tool,
- `app/api/tickets.py` exposes `GET /tickets` for the frontend tickets page.

The same side effect is therefore available through two runtime styles, but the live helpdesk workflow deliberately keeps it outside direct model control.

## Evaluation APIs

The backend has two evaluation views, both defined in [`apps/backend/app/api/evals.py`](../../apps/backend/app/api/evals.py).

### `GET /eval/runs`

This endpoint reads a local mirror of offline harness runs from:

- `apps/backend/eval/runs.jsonl`

Behavior:

- no file means an empty list,
- invalid JSON lines are skipped with suppression,
- results are reversed newest-first.

This is a convenience mirror, not the canonical source of truth.

### `GET /eval/foundry`

This endpoint calls `list_eval_runs(limit)` from [`apps/backend/app/services/foundry_evals.py`](../../apps/backend/app/services/foundry_evals.py).

This is the canonical user-facing path rendered by the frontend `/evals` page.

## Foundry eval listing service

`services/foundry_evals.py` reads evaluation metadata live from the Foundry project.

### Client construction

`_openai_client()` is memoized with `lru_cache(maxsize=1)` and builds:

- `AIProjectClient(endpoint=tenant_config().foundry_project_endpoint, credential=DefaultAzureCredential())`
- then `project.get_openai_client()`.

The source comment explicitly states that this uses the app's own identity, not OBO, because eval results are project-wide artifacts rather than per-user runtime data.

### Returned shape

`list_eval_runs(limit=8)`:

- lists recent eval definitions,
- lists recent runs for each eval,
- skips empty/no-score runs,
- returns run rows with:
  - `id`
  - `eval_name`
  - `status`
  - `created_at`
  - `report_url`
  - aggregate pass/fail counts
  - per-criterion summaries

If Foundry is not configured or not reachable, the function returns `[]` rather than raising, so the frontend can degrade gracefully.

## Relationship to the offline harness

The evaluation APIs are not the harness itself. They are readers over artifacts created elsewhere.

The actual harness lives in `apps/backend/eval/` and is documented in [Evaluation harness](../assurance/evaluation-harness.md). The important relationship is:

- `eval/run_eval.py --cloud` creates runs in the Foundry project,
- the backend reads those runs and exposes them to the frontend,
- the frontend evals page links users back to the Foundry portal report.

## Frontend consumers

- `/tickets` uses the backend tickets API to display persisted escalations.
- `/evals` uses the backend Foundry eval API to show recent assurance runs.

This makes both tickets and evals first-class workspace concepts, not buried backend-only artifacts.

## Focused tests

Representative tests include:

- `platform_hosted_bridge_test.py` and related hosted tests where eval visibility can matter after deployment.
- `approval_mode_test.py` for the ticket approval path feeding ticket persistence.
- `wiki_fidelity_test.py`, `wiki_freshness_test.py`, and `run_eval.py` self-tests for the broader eval ecosystem.

The repository does not isolate ticket tests in a dedicated file, so validation often happens through workflow and frontend behavior together.

## Validation

From `apps/backend/`:

```bash
uv run python -m eval.run_eval --self-test
```

For cloud-backed eval visibility:

```bash
uv run python -m eval.run_eval --cloud
```

Then verify the frontend `/evals` page or `GET /eval/foundry` reflects the new run.

## Related pages

- [Helpdesk workflow](helpdesk-workflow.md)
- [Evaluation harness](../assurance/evaluation-harness.md)
- [Frontend admin, evals, and tickets](../frontend/admin-evals-and-tickets.md)
