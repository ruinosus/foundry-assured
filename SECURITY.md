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

## Supported versions

This is a showcase; only `main` is maintained.
