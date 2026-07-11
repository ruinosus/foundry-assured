# Security policy

## Reporting a vulnerability

Please report security issues **privately** — open a [GitHub security advisory](https://docs.github.com/code-security/security-advisories)
on this repo, or email the maintainer. Do **not** open a public issue for a
vulnerability. We aim to acknowledge within a few business days.

## Handling secrets

- **No secrets in the repo.** `.env`, `.env.*`, `.azure/`, and key material are
  gitignored; never commit tokens, client secrets, or connection strings.
- Auth is **keyless** — `DefaultAzureCredential` locally and per-user **On-Behalf-Of**
  in the app. The only secret is the Entra **API client secret**, kept in the local
  `.env`, an azd environment value, or a GitHub Actions **secret** — never in source.
- CI authenticates to Azure with **OIDC federated credentials** (no stored Azure keys).

## Runtime safety

- The deployed hosted agent runs behind a **Content Safety guardrail** (RAI policy)
  that screens prompts and responses.
- The eval harness includes an **adversarial/jailbreak** suite (`run_eval --safety`)
  and a policy gate that fails on secret leakage or ungrounded answers.
- **Document-level access control (per-caller entitlement).** Retrieval is trimmed to
  what the signed-in user is entitled to — access **follows the source** (each doc's
  read groups), never classification logic in code. Enforcement is **defense in depth**:
  service-side identity passthrough (Foundry IQ trims from the caller's Entra token) plus
  an app-side trim (`app/agents/secure_search.py`), applied **before the model** so no
  prompt can change what's retrieved. Gated in CI (`.github/workflows/security-gates.yml`
  → `eval/access_control_test.py`): a single cross-group leak fails the build
  (`access_control_violations_max: 0`).
- **Red-team gate.** A corpus of injection / override / exfiltration prompts runs through
  the real retrieve + trim path (`eval/red_team_test.py`, same workflow); because the trim
  is pre-model and query-independent, no attack should pull cross-group content. The
  Attack-Success-Rate must stay under the ceiling (`redteam_asr_max`), gated in CI.

## Supported versions

This is a showcase; only `main` is maintained.
