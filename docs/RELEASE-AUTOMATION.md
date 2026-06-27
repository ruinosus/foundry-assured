# Release & deploy automation (enterprise-grade, no PAT)

How a merge becomes a versioned release and a gated production deploy — automatically,
with credentials a security team will sign off on. This is the pattern to copy into
your own repo (it has no secrets in it; you wire your own).

## The flow

```
 Conventional Commits on main
        │
        ▼
 release-please  ──opens/maintains──►  "release PR" (bumps version + CHANGELOG)
        │  (you merge it)
        ▼
 Release workflow  ──cuts──►  git tag + GitHub Release   ← gated, auditable
        │  (release: published)
        ▼
 Deploy workflow  ──►  production Environment gate  ──approve──►  azd deploy
```

Everything is automatic **up to the production gate**, which stays **manual on
purpose** — a human approves the go-live. That segregation of duties is a compliance
control (SOC 2 / ISO 27001 / SOX), not a limitation.

## The one gotcha: `GITHUB_TOKEN` can't trigger workflows

GitHub's built-in `GITHUB_TOKEN` is deliberately blocked from triggering *other*
workflow runs (an anti-recursion rule). So a GitHub Release created by release-please
**with `GITHUB_TOKEN` does not fire** the deploy workflow's `on: release`. The release
gets cut, but the deploy never starts.

To bridge release → deploy you need a token that is **not** the `GITHUB_TOKEN`. The
options, worst to best for security:

| Option | Token lifetime | Identity | Verdict |
| --- | --- | --- | --- |
| Personal Access Token (PAT) | up to 1 year / never | a person's account | works, **least secure** — avoid |
| **GitHub App installation token** | **~1 hour, auto-expires** | **a machine identity** | ✅ **recommended** |

A GitHub App is a first-class machine identity: scoped, least-privilege, not tied to
anyone's account (survives staff turnover; actions are audited as the App). The
workflow mints a short-lived token at run time — the only stored secret is the App's
private key, which itself only *mints* ephemeral tokens.

## Set up the GitHub App (one-time, per repo)

### 1. Create the App
Open **<https://github.com/settings/apps/new>** (or your org's *Settings → Developer
settings → GitHub Apps → New*) and set:

- **Name**: e.g. `myrepo-release` (must be globally unique)
- **Homepage URL**: your repo URL (any valid URL)
- **Webhook**: uncheck **Active** (not needed)
- **Repository permissions**:
  - **Contents** → **Read and write** (create tags, releases, the release-PR commits)
  - **Pull requests** → **Read and write** (open / maintain / label the release PR)
  - *(Metadata: Read-only — included automatically)*
- **Where can this GitHub App be installed?** → **Only on this account**

Click **Create GitHub App**.

### 2. App ID + private key
On the App page: note the **App ID** (a number), then **Generate a private key** —
it downloads a `.pem`. Treat it like a password (never commit it; rotate if leaked).

### 3. Install the App on the repo
App page → **Install App** → your account → **Only select repositories** → pick your
repo → **Install**.

### 4. Wire the credentials into the repo
Add a **variable** and a **secret** (Settings → Secrets and variables → Actions, or
the CLI):

```bash
gh variable set RELEASE_APP_ID      --repo <owner>/<repo> --body "<APP_ID>"
gh secret   set RELEASE_APP_PRIVATE_KEY --repo <owner>/<repo> < /path/to/key.pem
```

That's it. `.github/workflows/release.yml` already mints the token when these exist:

```yaml
- uses: actions/create-github-app-token@v2
  id: app-token
  if: ${{ vars.RELEASE_APP_ID != '' }}
  with:
    app-id: ${{ vars.RELEASE_APP_ID }}
    private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}

- uses: googleapis/release-please-action@v4
  with:
    token: ${{ steps.app-token.outputs.token || secrets.GITHUB_TOKEN }}
    # ...
```

It is a **graceful upgrade**: until the App exists, the App step is skipped and the
token falls back to `GITHUB_TOKEN` (the release still cuts; you just dispatch the
deploy manually). Once the var + secret are set, the next release cuts *and* triggers
the deploy — no workflow change required.

## Safety-net: cut the release even if release-please balks

`release-please-action@v4` will, in some states, refuse to tag a just-merged release
PR — `There are untagged, merged release PRs outstanding - aborting` — and the release
never gets cut. `release.yml` has a follow-up step that, if the manifest version has
no release yet, cuts it from the CHANGELOG and marks the merged release PR
`autorelease: tagged` so the next run reconciles. It uses the same App token, so its
cut also triggers the deploy. This makes the release deterministic regardless of the
action's flakiness.

## The rest of the security posture (already in this template)

- **Cloud auth via OIDC** — the deploy authenticates to Azure with short-lived
  federated tokens; no cloud secret is stored (see `CONTRIBUTING.md`).
- **Environment protection** — the `production` Environment requires a reviewer
  before any deploy runs (the manual gate above).
- **Branch protection** — required status checks, no direct pushes to `main`.
- **Least-privilege `permissions:`** declared per workflow.
- **No secrets in the repo** — only `.env.example` templates; real values are repo
  secrets / the App private key, set per clone.

Net: merge a release PR → versioned release cut by a short-lived machine token →
deploy fires → a human approves the production gate → live. Auditable, least-privilege,
and reproducible by anyone who clones the template.
