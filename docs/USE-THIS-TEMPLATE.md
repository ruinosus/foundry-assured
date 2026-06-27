# Use this template

This repo is a **GitHub template**. Click **Use this template → Create a new
repository**, then run the checklist below. Code copies; **infrastructure, identities
and secrets do not** — you provision your own (that isolation is the point: every repo
created from the template is independent, with no shared credentials).

> The domain is swappable — see [`CUSTOMIZE.md`](./CUSTOMIZE.md) for the four swap
> points (corpus, prompts, the action/ticket, identity). This guide is just the
> *infra + CI/CD* wiring.

## 1. Provision Azure (your own resources)

```bash
azd auth login && az login
azd up            # Foundry project + model + Azure AI Search + Storage + ACR + Container Apps
```

`azd` generates unique resource names for *your* environment — nothing from the
template's environment carries over.

## 2. Data-plane objects + sign-in

```bash
./scripts/setup-entra.sh   # optional: Entra sign-in + OBO (skip to run without auth)
./scripts/bootstrap.sh     # fills .env from azd outputs, ingests the KB, provisions memory
```

See [`DEPLOYMENT.md`](./DEPLOYMENT.md) for the manual steps behind the scripts and the
cost table.

## 3. CI/CD identities & protections (one-time, in your new repo)

| What | Why | Where |
| --- | --- | --- |
| **OIDC federated credential** | deploy authenticates to Azure with short-lived tokens, no stored cloud secret | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| **Branch protection** on `main` | required checks, no direct pushes | repo Settings → Branches |
| **`production` Environment** + reviewer | the manual deploy gate (segregation of duties) | repo Settings → Environments |
| **GitHub App** for release→deploy | short-lived machine token cuts the release *and* triggers deploy (no PAT) | [`RELEASE-AUTOMATION.md`](./RELEASE-AUTOMATION.md) |

All four are least-privilege and contain **no secrets in the repo** — you set repo
secrets/vars per clone.

## 4. Reset the version history (start at your own 0.x)

The template ships this project's `CHANGELOG.md` and `.release-please-manifest.json`.
For a clean start in your repo:

```bash
: > CHANGELOG.md
echo '{ ".": "0.0.0" }' > .release-please-manifest.json
git commit -am "chore: reset release history for new project"
```

The first Conventional-Commit `feat:`/`fix:` you merge will open release-please's first
release PR; merging it cuts your `v0.1.0` (or `v0.0.1`) and — once the GitHub App from
step 3 is wired — triggers the gated deploy. See
[`RELEASE-AUTOMATION.md`](./RELEASE-AUTOMATION.md).

## 5. (Optional) Try it with no Azure first

```bash
npm --prefix apps/frontend run demo   # AG-UI replay via CopilotKit aimock — zero cloud
```

---

That's the whole bring-up: **provision → data + sign-in → CI/CD identities → reset
version → ship**. Everything after is the normal develop-on-`main`, merge-a-release-PR,
approve-the-gate loop.
