---
title: Use-case walkthrough — a company adopts the mechanism
description: A worked, fictional example of the whole assurance mechanism end to end, separating generic code from the company's own data.
type: explanation
audience: evaluator
status: stable
updated: 2026-06-27
---

# Use-case walkthrough — a company adopts the mechanism end to end

A concrete, fictional example of the whole mechanism, so it's clear **what** each piece
does and **how** — and, crucially, what is *generic code* vs *the company's own data*.

> The golden rule: **the code is domain-agnostic; the company brings the data** (corpus,
> identities, and the *access* of who-can-see-what). Nothing about the company lives in
> the mechanism's source — and there is **no classification logic in the code**: access
> *follows the source*.

> Visual version of this same story: [`use-case-demo.html`](./use-case-demo.html).

---

## The company

**Meridian Freight** — a logistics platform. Its knowledge is spread across **SharePoint,
ADLS/Blob and repositories**, and (like any real org) each source already has its own
**native access control**: the people/teams who can read it. The mechanism **inherits that
access** — it never invents a "tier". The common thread is the **Entra ID identity**: the
same person across every source.

For the repos specifically, each one has a real reader group in Entra/AD — the team that
can clone/read it. That existing access **is** what gates the doc; we don't classify on top.

| Repo | Stack | Who can read it today (existing reader group) |
| --- | --- | --- |
| `mf-developer-portal` | Next.js | `all-employees` |
| `mf-tracking-api` | .NET | `eng-platform` |
| `mf-routing-service` | Go | `eng-platform` |
| `mf-pricing-engine` | Python | `eng-pricing` |
| `mf-fraud-rules` | Python | `sec-fraud` |
| `mf-public-sdk` | TypeScript | `all-employees` |

The reader-group column is **not a label someone made up** — it's the repo's real read
team. That's the professional basis: *access follows the source*. Note `eng-platform` ≠
`eng-pricing` even though both are "internal" engineering teams: the cut is by **real
group**, not by some made-up level.

---

## The flow (what + how)

### 1. Provision the cloud (generic code, their cloud)

```bash
azd up
```

Stands up **Meridian's own** Foundry project, Azure AI Search, Storage, Container Apps —
all from the template's Bicep. Nothing from anyone else's environment carries over.

### 2. Wire identities (their groups)

Meridian already has `eng-platform`, `eng-pricing`, `sec-fraud`, etc. They map each group
**name → Entra object-ID** in config (no code change) so the mechanism can stamp the index
with real IDs:

```
# COCKPIT_ACL_GROUP_MAP — comma-separated name:object-id pairs
COCKPIT_ACL_GROUP_MAP=all-employees:<oid>,eng-platform:<oid>,eng-pricing:<oid>,sec-fraud:<oid>
```

> If they *didn't* have groups, `infra/entra/entra.bicep` / `create-acl-identities.sh`
> create demo ones — but a real org plugs in groups it already manages.

### 3. Generate the wiki — access is **inherited from each repo**

```bash
uv run python -m app.knowledge.wiki_builder --repo ../mf-pricing-engine --component mf-pricing-engine --version v1.0.0 --groups eng-pricing --out ./wiki-out
```

The generator reads the **real source** and writes a faithful, cited wiki. As it does, it
records **which group(s) can read the source repo** into the bundle manifest — so the wiki
page inherits the repo's access. Meridian's `mf-pricing-engine` was readable only by
`eng-pricing`, so its bundle is born with that group:

```jsonc
// wiki-out/mf-pricing-engine/v1.0.0/manifest.json  ← DATA, produced from the repo
{
  "key": "mf-pricing-engine-v1.0.0",
  "component": "mf-pricing-engine",
  "groups": ["eng-pricing"],          // ← inherited from the repo's reader team(s)
  "pages": [ ... ]
}
```

No markers, no guessing — the manifest's `groups` came from the repo's read teams.

### 4. (Or) the owner declares access explicitly — still data, never code

If the access can't be auto-inherited, the data owner provides one external file
(gitignored, like the corpus) mapping **component → reader group(s)**. The mechanism reads
it; the code stays generic:

```jsonc
// meridian-acl.json   (path → COCKPIT_ACL_CLASSIFICATION; gitignored)
{
  "mf-developer-portal": ["all-employees"],
  "mf-public-sdk":       ["all-employees"],
  "mf-tracking-api":     ["eng-platform"],
  "mf-routing-service":  ["eng-platform"],
  "mf-pricing-engine":   ["eng-pricing"],
  "mf-fraud-rules":      ["sec-fraud"]
}
```

Anything **not** listed (no declared access) falls to `cockpit_acl_default_groups` — and
if that's empty it's **fail-closed**, so an undeclared doc never leaks by omission.

### 5. Ingest — the mechanism just reads the declared groups and stamps

```bash
COCKPIT_ACL_CLASSIFICATION=./meridian-acl.json uv run python -m app.knowledge.ingest_cockpit
```

For every document it reads the **owner-declared groups** (manifest or the file), resolves
each group **name → object-ID** via `COCKPIT_ACL_GROUP_MAP`, and stamps the index `groups`
field + enables query-time trimming. **`acl_setup.py` (which ingest calls) contains zero
classification logic** — it's pure read-the-data-and-enforce.

### 6. Consume — each person sees only their entitlement

Meridian devs use the chat. The agent retrieves **as the signed-in user** (their token is
passed to the KB), and access is enforced **defense-in-depth**: Foundry IQ trims
service-side from the passed identity, and `secure_search.py` trims app-side too:

| Who asks "explain the pricing algorithm" | What the KB returns | Why |
| --- | --- | --- |
| Dana (in `eng-pricing`) | the real pricing-engine docs, cited | entitled |
| Sam (only `eng-platform`) | "I don't have that in the knowledge I can access" | `mf-pricing-engine` reads `eng-pricing`; Sam isn't in it |
| Public contractor (`all-employees`) | only the developer-portal / SDK docs | only public-group docs |

Same question, same agent — **different answers by identity**. The cut is by **group**,
not by job title or seniority: Sam is a senior engineer, just *on another team*. The agent
literally cannot surface what the caller isn't cleared for.

### 7. Measure — the gates (their golden, gitignored)

- **Quality**: groundedness + completeness + retrieval-recall gates in CI (`eval/run_eval.py`).
- **Security**: the access-control gate (`eval/access_control_test.py`) asserts Sam never
  retrieves a doc he isn't entitled to — a single leak fails the build
  (`access_control_violations_max: 0`).

### 8. Defend (red-team) — the trim is injection-proof

The red-team gate (`eval/red_team_test.py`) throws prompt-injection / exfiltration at the
chat; because the trim happens at the retrieval layer *before* the model and is
query-independent, no poisoned doc or jailbreak can make it leak across groups. The
Attack-Success-Rate gate (`redteam_asr_max`) keeps merges honest.

---

## What was *generic code* vs *Meridian's data*

| Generic code (in the template repo) | Meridian's data (external, gitignored) |
| --- | --- |
| `wiki_builder.py`, `ingest_cockpit.py`, `acl_setup.py`, `secure_search.py`, the eval/red-team harness | the **corpus** (their wikis) |
| group-name **→ object-ID map mechanism** (reads `COCKPIT_ACL_GROUP_MAP`) | the **access** of each source (SharePoint/ADLS native; repos inherited from origin) + the **group object-IDs** (`.env`) |
| read-the-groups-and-enforce | the **groups** themselves (manifest `groups` / `meridian-acl.json`) |
| the agent, prompts, gates | their **golden set** + thresholds |

Meridian cloned the template, pointed it at **their** repos/sources, plugged in **their**
groups and the access each source already had, and shipped — **without editing a line of
the mechanism**. That's the whole point: there is no classification logic in the code;
access follows the source, the company supplies the data, the mechanism supplies the
(measured) guarantees.
