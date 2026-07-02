# Foundry Assured — E2E (Playwright)

Browser end-to-end tests that drive the **deployed** cloud app through real Entra sign-in and
each domain, capturing **screenshots + video + trace** to `./artifacts/` so a run can be reviewed
step-by-step.

## Run

```bash
cd e2e
npm install
npm run install:browser            # one-time: downloads chromium

# creds never live in the repo — pass them at run time (test users: TEST-CREDENTIALS.local.md)
export E2E_BASE_URL="$(cd ../apps/backend && azd env get-value WEB_URL)"
export E2E_USER="cockpit-test-a@jeffersonbarnabegmail.onmicrosoft.com"
export E2E_PASS='…'                # from TEST-CREDENTIALS.local.md (gitignored)

npm test                           # runs smoke.spec.ts
npm run report                     # open the HTML report
```

## Artifacts (open these to follow a run)

| Path | What |
|---|---|
| `artifacts/steps/NN-*.png` | named, ordered screenshots of every step (the "prints") |
| `artifacts/report/` | Playwright HTML report (`npm run report`) |
| `artifacts/results/` | per-test `trace.zip` + video |

## Scope

- **Now (smoke):** sign in → visit helpdesk / cockpit / selfwiki / platform → one grounded
  helpdesk answer. One serial flow in a single context (MSAL token lives in `sessionStorage`).
- **Next:** HITL approval (create_ticket), ACL A-sees / B-doesn't (two test users via per-user
  `storageState` + sessionStorage capture), evals, and the shared-mode admin/tenant flow.

## Notes

- The deployed app **scales to zero** — the first hit cold-starts (~30s+); timeouts are generous.
- If a test user has MFA enforced, the scripted password login stops at the MFA prompt. Use a
  password-only test user, or capture a `storageState` from a manual login (fase 2).
