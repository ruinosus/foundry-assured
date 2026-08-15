---
type: frontend-demo-mode
title: Frontend demo mode
description: Mocked frontend runtime that replays recorded AG-UI fixtures with no Azure provisioning and no Python backend.
tags: [frontend, demo, fixtures, testing]
---

# Frontend demo mode

The repository includes a supported demo path that runs the real frontend UI without requiring Azure provisioning or a live Python backend. This is a distinct runtime mode, not just a developer convenience flag.

Core evidence:

- `apps/frontend/package.json` exposes `demo` and `demo:record` scripts.
- `apps/frontend/lib/demo.ts` defines `demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1"`.
- `apps/frontend/demo/fixtures/` stores replayable AG-UI fixture files.
- `scripts/demo.sh` runs replay mode.
- `scripts/demo-record.sh` records new fixtures by proxying a live backend.

## Runtime model

Demo mode uses CopilotKit `aimock` to replay recorded AG-UI fixtures. The frontend still renders the real console, chat components, and evidence UI.

That means demo mode is useful for:

- showing the product without provisioning Azure,
- validating UI flow rendering,
- sharing deterministic examples,
- reviewing the narrative and interaction model.

It is not a replacement for backend, auth, or retrieval validation.

## Toggle

The frontend decides whether it is in demo mode through `NEXT_PUBLIC_DEMO_MODE=1`, exposed in `lib/demo.ts`.

The scripts set additional environment variables so CopilotKit points to the local replay server instead of the backend.

## `scripts/demo.sh`

This script is the primary no-Azure demo launcher.

Responsibilities:

1. verify `npx` and `python3` are available,
2. verify at least one fixture exists under `apps/frontend/demo/fixtures/`,
3. install frontend dependencies if needed,
4. merge all recorded fixture JSON into one temporary `aimock` config,
5. run `aimock --config ...` on a local mock port,
6. launch the Next.js frontend with:
   - `AGUI_URL=http://localhost:$PORT_MOCK/agui`
   - `HOSTED_AGUI_URL=http://localhost:$PORT_MOCK/agui`
   - `NEXT_PUBLIC_DEMO_MODE=1`

So the browser talks to replayed AG-UI streams while the UI remains unchanged.

## `scripts/demo-record.sh`

This script records new fixtures from a real backend.

Responsibilities:

- run `llmock` in AG-UI record mode,
- proxy requests to a real upstream endpoint, defaulting to `http://localhost:8000/helpdesk`,
- write fixtures into `apps/frontend/demo/fixtures/`.

The source comments specify the intended recording posture:

- the backend should run in no-auth mode,
- it should still use real Foundry and KB resources,
- the operator should drive both a grounded question and a ticket-plus-approval flow,
- then commit the resulting fixtures.

That is why the README can claim the fixtures are replayed from real runs rather than hand-authored mocks.

## What demo mode preserves

Because it replays AG-UI streams, demo mode can preserve:

- chat transcript rendering,
- streamed workflow steps,
- grounded answer presentation,
- evidence panel source rendering when events are present,
- hosted/live UI layout parity,
- approval-interrupt rendering if the recorded fixture includes it.

## What demo mode does not validate

Demo mode does **not** validate:

- backend auth and OBO,
- shared-mode tenant resolution,
- live retrieval or ACL trimming,
- real ticket persistence,
- live hosted-agent responses,
- Graph-backed admin operations,
- current backend correctness after fixture recording time.

It is a replay path, not an integration test.

## Relationship to testing

Demo mode complements rather than replaces:

- local live development,
- backend eval suite,
- Playwright E2E tests in `e2e/`.

It is best thought of as a deterministic UI demonstration harness.

## Validation

From `apps/frontend/`:

```bash
npm run demo
```

To refresh fixtures:

```bash
npm run demo:record
```

## Related pages

- [Frontend application overview](application-overview.md)
- [Domain console](domain-console.md)
- [End-to-end and validation](../testing/end-to-end-and-validation.md)
