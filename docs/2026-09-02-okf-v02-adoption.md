# OKF v0.2 Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Create an isolated workspace first via `superpowers:using-git-worktrees`. Do not start on `main`.

**Goal:** Make this repository emit OKF v0.2 trust metadata on every generated concept, stop discarding frontmatter on the path to the knowledge base, and make the conformance gate stop reporting green for things it did not measure.

**Architecture:** Three phases separated by two halting decision gates. Phase 0 fixes claims the repo makes that are not true — no design decisions, safe to run start to finish. Phase 1 emits the `generated`/`verified` trust family, which requires a decision about ADR-023 first (Gate A). Phase 2 preserves frontmatter into `wiki-bundle/` and projects it into the search index, which rests on a hypothesis that must be tested before the phase is designed (Gate B).

**Tech Stack:** Python 3.12 · `uv` · pytest · FastAPI · Azure AI Search · Foundry Agent Framework · GitHub Actions.

---

## How to read this plan

This plan was written from `docs/OKF-CONFORMANCE-FINDINGS.md`, not from the source
files. Every `path:line` reference below is **quoted from that report** and may have
drifted. Therefore:

- **Every task begins with a verification step** that opens the cited file and confirms
  the anchor. If the anchor does not match, **stop and report** — do not search for
  something similar and proceed. A drifted anchor means this plan's assumption about
  that file is stale, and the task's design may be wrong, not just its line number.
- **New files carry complete code.** Tasks that create a module or a test contain the
  full implementation; write them as given.
- **Edits carry the intended end state, not a diff.** For modifications the plan
  specifies exactly what the code must do afterwards and what the anchor looks like now.
  You write the edit against the real file. This is deliberate: a fabricated diff against
  an unread file is worse than a precise specification of behavior.
- **The two gates halt.** At Gate A and Gate B you stop, report, and wait. They are not
  checkpoints to summarize past — they are decisions that are not yours to make, and
  Phase 2's design literally depends on Gate B's answer.

---

## Global Constraints

- **Do not touch access control.** No frontmatter field may gain influence over an
  authorization decision in this plan. OKF trust tiers are advisory and explicitly not
  access control (`SPEC.md:410`). The existing `groups:` path (`frontmatter.py:60`,
  `ingest.py:167-177`, ADR-031) is out of scope and must be left byte-identical.
- **Any search filter is ANDed with `permissionFilter`, never substituted for it**
  (`acl_setup.py:125`). A filter change that can widen a result set for any caller is a
  failed task regardless of tests passing.
- **`docbundle.schema.json` is a vendored contract.** Do not modify it. Gate B exists
  because of it.
- **OKF version targeted: v0.2**, as declared by `SPEC.md:3` at commit
  `ad30107c31c06aec8a7d5636e0d1058118604e6f`.
- **Actor convention is normative** (`SPEC.md:489-501`): `<producer>/<version>` for
  agents and tools, `human:<id>` for people, `process:<id>` for automated processes.
  Trust tiers key off the `human:` prefix, so a machine actor must never be written with
  it.
- **All timestamps are ISO 8601 with an explicit UTC offset** (`SPEC.md:284-285`). A bare
  date is not conformant.
- **Do not add a dependency.** Everything here uses `pyyaml`, `pytest` and the stdlib,
  all already present.
- **The vendored validator is read-only.** `apps/backend/vendor/okf_validate.py` is a
  third-party artifact (`vendor/README.md:11-14`). If it needs a behavior change, that is
  a finding to report, not an edit to make.
- **Commit after every task.** Conventional commits, one task per commit.

---

# PHASE 0 — Stop reporting green for what was not measured

No design decisions. Safe to execute start to finish without stopping. This phase
changes no wiki output and no runtime behavior; it changes what CI tells you.

**Rationale:** The gate currently prints `✅ os 4 bundles são OKF v0.2 conformantes`
while (a) one of those bundles declares `okf_version: "0.1"`, (b) the warning saying so
is discarded because the gate only fails on errors, and (c) the bundle users actually
query is not in the list and its absence is invisible in the output. That is the same
failure `docs/CASE-STUDY-LLM-WIKI-LOOP.md` documents: a green number asserting more than
it measured. Everything downstream in this plan is judged by that gate, so it has to be
honest before it is trusted.

---

### Task 0.1: Make the conformance gate fail on a version-declaration mismatch

**Files:**
- Modify: `apps/backend/tests/knowledge/okf_conformance_test.py` (anchors: bundle list at
  `:40-50`, pass/fail decision at `:88-90`)
- Read only: `apps/backend/vendor/okf_validate.py` (warning emitted at `:331-334`)

**Interfaces:**
- Produces: a gate that exits non-zero when any bundle declares an `okf_version` other
  than the version the validator checked against. Later tasks rely on this gate being
  trustworthy.

- [ ] **Step 1: Verify the anchors**

Run:
```bash
sed -n '35,60p' apps/backend/tests/knowledge/okf_conformance_test.py
sed -n '80,95p' apps/backend/tests/knowledge/okf_conformance_test.py
sed -n '325,340p' apps/backend/vendor/okf_validate.py
```
Expected: a hand-maintained list of four bundle directories; a pass/fail branch that
inspects only errors; a validator warning whose text mentions `okf_version` and `§12`.

If the gate already fails on version mismatch, mark this task complete and record that
the finding was stale.

- [ ] **Step 2: Write the failing test**

Create `apps/backend/tests/knowledge/okf_gate_honesty_test.py`:

```python
"""The conformance gate must not report success for things it did not check.

Guards two failure modes found in the 2026-09-02 OKF audit:
  1. A bundle declaring okf_version != the version the validator checked against
     produced only a warning, which the gate discarded.
  2. Wiki artifact directories outside the hand-maintained list were silently
     unmeasured while the gate printed a blanket success message.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET_OKF_VERSION = "0.2"


def _declared_okf_version(bundle: Path) -> str | None:
    """Return the okf_version declared in a bundle-root index.md, if any.

    SPEC.md:512-513 permits frontmatter in an index.md only at the bundle root,
    and only to carry okf_version.
    """
    index = bundle / "index.md"
    if not index.is_file():
        return None
    text = index.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    _, _, rest = text.partition("---")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return None
    data = yaml.safe_load(block) or {}
    version = data.get("okf_version")
    return None if version is None else str(version)


def _gated_bundles() -> list[Path]:
    """The bundle list the conformance gate actually checks."""
    from tests.knowledge import okf_conformance_test as gate

    for attr in ("BUNDLES", "BUNDLE_DIRS", "OKF_BUNDLES"):
        if hasattr(gate, attr):
            return [Path(b) if isinstance(b, (str, Path)) else b for b in getattr(gate, attr)]
    pytest.fail(
        "okf_conformance_test exposes no module-level bundle list; "
        "expose one (e.g. BUNDLES) so the honesty gate can read it."
    )


@pytest.mark.parametrize("bundle", _gated_bundles(), ids=lambda p: str(p))
def test_declared_version_matches_validated_version(bundle: Path) -> None:
    path = bundle if bundle.is_absolute() else REPO_ROOT / bundle
    declared = _declared_okf_version(path)
    if declared is None:
        return  # declaring is optional (SPEC.md:776-780)
    assert declared == TARGET_OKF_VERSION, (
        f"{path.relative_to(REPO_ROOT)}/index.md declares okf_version "
        f"{declared!r} but the gate validates against v{TARGET_OKF_VERSION}. "
        "Either the declaration or the target is wrong; a warning is not enough."
    )


def test_gate_message_does_not_claim_unmeasured_coverage() -> None:
    """The success message must not imply coverage beyond the checked list."""
    source = (
        REPO_ROOT / "apps/backend/tests/knowledge/okf_conformance_test.py"
    ).read_text(encoding="utf-8")
    banned = re.compile(r"(todos os bundles|all bundles|o repositório é OKF)", re.I)
    assert not banned.search(source), (
        "Gate output claims repository-wide conformance. It measures a fixed list; "
        "say how many and name them."
    )
```

- [ ] **Step 3: Run it and confirm the version test fails**

Run:
```bash
cd apps/backend && uv run pytest tests/knowledge/okf_gate_honesty_test.py -v
```
Expected: `test_declared_version_matches_validated_version[...openwiki]` FAILS with the
`'0.1'` vs `'0.2'` message. The second test may pass; that is fine.

If `_gated_bundles` fails instead because no module-level list is exposed, do Step 4
first, then re-run.

- [ ] **Step 4: Expose the bundle list and make the gate fail on mismatch**

In `okf_conformance_test.py`:
- Lift the four hard-coded bundle directories (`:40-50`) into a module-level constant
  named `BUNDLES`, preserving the existing comment that justifies why it is a list and
  not a glob.
- At the pass/fail decision (`:88-90`), treat a warning whose text matches
  `okf_version` as an **error** for gating purposes. Other warnings stay warnings.
- Change the success message so it names the count and the directories it checked, and
  makes no claim about anything else. Do not use the words banned by the test above.

Do **not** modify `vendor/okf_validate.py`. The validator is right to call this a
warning; the gate is what decides severity.

- [ ] **Step 5: Confirm the gate now fails for the right reason**

Run:
```bash
cd apps/backend && uv run python -m tests.knowledge.okf_conformance_test
```
Expected: non-zero exit, output naming `openwiki/index.md` and the version mismatch.
This failure is **correct and expected** — Task 1.5 resolves it. Do not fix it here by
editing `openwiki/index.md`; declaring v0.2 on a bundle that carries no v0.2 fields is
the same false claim in the other direction.

- [ ] **Step 6: Record the known-failing gate**

Add a short note to `docs/OKF-CONFORMANCE-FINDINGS.md` under §7 defect 2 stating that
the gate now fails on the mismatch by design, and that Task 1.5 of
`docs/superpowers/plans/2026-09-02-okf-v02-adoption.md` closes it.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/tests/knowledge/okf_gate_honesty_test.py \
        apps/backend/tests/knowledge/okf_conformance_test.py \
        docs/OKF-CONFORMANCE-FINDINGS.md
git commit -m "fix(okf): gate fails on okf_version mismatch instead of warning"
```

---

### Task 0.2: Make the gate name what it does not cover

**Files:**
- Modify: `apps/backend/tests/knowledge/okf_conformance_test.py`
- Test: `apps/backend/tests/knowledge/okf_gate_honesty_test.py` (extend)

**Interfaces:**
- Consumes: `BUNDLES` from Task 0.1.
- Produces: gate output that lists every wiki-shaped directory it deliberately excludes,
  with a reason. Task 2.2 removes one entry from that exclusion list.

- [ ] **Step 1: Write the failing test**

Append to `okf_gate_honesty_test.py`:

```python
KNOWN_WIKI_DIRS = {
    "openwiki",
    "knowledge/corpus",
    "apps/backend/agents/assured/flows",
    "apps/backend/agents/assured/copilots",
    "knowledge/wiki-bundle/foundry-assured/v0.20260819",
    "apps/backend/agents/assured/guardrails",
    "apps/backend/agents/assured/personas",
}


def test_every_known_wiki_dir_is_gated_or_explicitly_excluded() -> None:
    """A directory is either checked or named as excluded. Silence is not an option."""
    from tests.knowledge import okf_conformance_test as gate

    gated = {str(Path(b)).replace("\\", "/").strip("/") for b in _gated_bundles()}
    gated = {g.split("foundry-assured/")[-1] if False else g for g in gated}
    excluded = getattr(gate, "EXCLUDED_BUNDLES", None)
    assert isinstance(excluded, dict), (
        "okf_conformance_test must expose EXCLUDED_BUNDLES: dict[str, str] "
        "mapping each unchecked wiki-shaped directory to the reason it is unchecked."
    )
    accounted = {p.rstrip("/") for p in gated} | {p.rstrip("/") for p in excluded}
    missing = {d for d in KNOWN_WIKI_DIRS if not any(a.endswith(d) for a in accounted)}
    assert not missing, (
        f"Wiki-shaped directories neither gated nor explicitly excluded: {sorted(missing)}. "
        "Add them to BUNDLES or to EXCLUDED_BUNDLES with a reason."
    )
    for path, reason in excluded.items():
        assert reason.strip(), f"{path} is excluded with no reason given."
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/backend && uv run pytest tests/knowledge/okf_gate_honesty_test.py::test_every_known_wiki_dir_is_gated_or_explicitly_excluded -v`
Expected: FAIL — `EXCLUDED_BUNDLES` does not exist.

- [ ] **Step 3: Add the exclusion map**

In `okf_conformance_test.py`, add a module-level `EXCLUDED_BUNDLES: dict[str, str]`
containing exactly these three entries, with these reasons (the reasons are findings,
copy them faithfully):

- `knowledge/wiki-bundle/foundry-assured/v0.20260819` → frontmatter is stripped at
  ingest by `adapt_openwiki.py:22-24`; see Gate B of the OKF adoption plan. **This is
  the artifact the `selfwiki` domain queries.**
- `apps/backend/agents/assured/guardrails` → application data, deliberately not
  AgentSchema concepts (`guardrails/response-language.md:2`).
- `apps/backend/agents/assured/personas` → same.

Print the exclusion list in the gate's output, every run, not only on failure.

- [ ] **Step 4: Run the full gate and confirm the exclusions are printed**

Run: `cd apps/backend && uv run python -m tests.knowledge.okf_conformance_test`
Expected: exclusions listed with reasons; still exits non-zero from Task 0.1's version
mismatch.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/tests/knowledge/
git commit -m "fix(okf): gate names the wiki dirs it does not check, with reasons"
```

---

### Task 0.3: Repair the unparseable frontmatter block

**Files:**
- Modify: `docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md:1-10`
- Test: `apps/backend/tests/knowledge/okf_gate_honesty_test.py` (extend)

**Rationale:** The `description` value contains `API oficial: 23 operações` — a `: `
inside an unquoted YAML scalar, so `yaml.safe_load` raises at line 2. It has no runtime
effect today only because `docs/` is never ingested; `ingest.py:162-165` would `sys.exit`
on it. A naive `startswith("---")` check counts the file as having frontmatter, which is
how it survived.

- [ ] **Step 1: Confirm the failure mode**

Run:
```bash
cd apps/backend && uv run --with pyyaml --no-project python -c "
import sys, yaml, pathlib
p = pathlib.Path('../../docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md')
t = p.read_text(encoding='utf-8')
block = t.split('---')[1]
try:
    yaml.safe_load(block); print('PARSES — finding is stale')
except yaml.YAMLError as e:
    print('RAISES:', e)
"
```
Expected: `RAISES: mapping values are not allowed here`.

- [ ] **Step 2: Write the repo-wide failing test**

Append to `okf_gate_honesty_test.py`:

```python
def test_every_frontmatter_block_in_docs_parses() -> None:
    """A file that looks like it has frontmatter must actually have parseable frontmatter.

    ingest.py:162-165 exits on an unparseable block; a naive startswith('---')
    check does not catch it. Content conformance is out of scope here — this
    asserts only that the YAML parses.
    """
    broken: list[str] = []
    for md in sorted((REPO_ROOT / "docs").rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        _, _, rest = text.partition("---")
        block, sep, _ = rest.partition("\n---")
        if not sep:
            broken.append(f"{md.relative_to(REPO_ROOT)}: unterminated frontmatter block")
            continue
        try:
            yaml.safe_load(block)
        except yaml.YAMLError as exc:
            first = str(exc).splitlines()[0]
            broken.append(f"{md.relative_to(REPO_ROOT)}: {first}")
    assert not broken, "Unparseable frontmatter:\n" + "\n".join(broken)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd apps/backend && uv run pytest tests/knowledge/okf_gate_honesty_test.py::test_every_frontmatter_block_in_docs_parses -v`
Expected: FAIL naming `2026-08-17-user-managed-agents-and-knowledge-design.md`. If it
names additional files, fix those too in Step 4 — the audit counted 60 §11.1 errors in
`docs/`, but most are missing blocks (out of scope), not broken ones.

- [ ] **Step 4: Quote the value**

Wrap the `description` value in double quotes so the embedded `: ` is literal. Change
nothing else — not the wording, not the other keys.

- [ ] **Step 5: Confirm it passes**

Run: `cd apps/backend && uv run pytest tests/knowledge/okf_gate_honesty_test.py -v`
Expected: this test PASSES; the version-mismatch test still fails (expected until 1.5).

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md \
        apps/backend/tests/knowledge/okf_gate_honesty_test.py
git commit -m "fix(docs): quote description containing a colon so frontmatter parses"
```

---

### Task 0.4: Correct the two documentation misstatements

**Files:**
- Modify: `docs/superpowers/specs/2026-08-27-docbundle-vs-okf-medicao.md:12`
- Modify: `CLAUDE.md` (the "ADRs 001–023" string)

- [ ] **Step 1: Verify both anchors**

Run:
```bash
sed -n '10,14p' docs/superpowers/specs/2026-08-27-docbundle-vs-okf-medicao.md
grep -n "001–023\|001-023" CLAUDE.md
ls docs/adr/ | grep -c '^ADR-'
```
Expected: a line attributing SPEC.md to `GoogleCloudPlatform/knowledge-catalog`; an ADR
range string in `CLAUDE.md`; an ADR count of 33.

- [ ] **Step 2: Fix the repo attribution**

Change the citation to `GoogleCloudPlatform/open-knowledge-format`, and append the
pinned commit `ad30107c31c06aec8a7d5636e0d1058118604e6f`. Keep the line count (1006) —
it is correct and is the evidence that the right file was read.

- [ ] **Step 3: Fix the ADR range**

Update `CLAUDE.md` to the real range shown by the `ls` above. Verify the top of the range
against the highest-numbered file, not against this plan.

- [ ] **Step 4: Confirm no other stale reference exists**

Run: `grep -rn "knowledge-catalog" . --include='*.md' --include='*.py' --include='*.ts'`
Expected: no hits. If any remain, fix them in this task.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-27-docbundle-vs-okf-medicao.md CLAUDE.md
git commit -m "docs: correct OKF spec repo attribution and ADR range"
```

---

### Task 0.5: Reconcile the writer skill with the pipeline that overrides it

**Files:**
- Modify: `apps/backend/app/modules/knowledge/skills/wiki-page-writer/SKILL.md:47-54`
- Read only: `apps/backend/app/modules/knowledge/internal/wiki_builder.py:198-200,354`

**Rationale:** The skill mandates VitePress frontmatter (`title`, `description`, no
`type`), and `wiki_builder.py:354` instructs the model to emit no frontmatter at all —
in the same pipeline that loads the skill into the writer prompt (`:198-200`). One of
the two instructions is dead, and which one wins is invisible from either file. The
skill's own template would also fail §11.2 for lacking `type`.

**Note:** This task only removes the contradiction. It does not decide what frontmatter
the writer emits — that is Task 1.2, after Gate A.

- [ ] **Step 1: Read both sides**

Run:
```bash
sed -n '40,60p' apps/backend/app/modules/knowledge/skills/wiki-page-writer/SKILL.md
sed -n '195,205p;350,360p' apps/backend/app/modules/knowledge/internal/wiki_builder.py
```
Expected: a frontmatter template in the skill; a prompt line saying `sem frontmatter
VitePress`; a `_writer_rules` function reading the skill file into the prompt.

- [ ] **Step 2: Remove the dead instruction from the skill**

Delete the VitePress frontmatter template from the skill and replace it with one
sentence stating that frontmatter is applied by the pipeline, not by the writer, and
naming `wiki_builder._page_prompt` as the authority. Leave the citation-depth rules
(`:67-73`) untouched — they are live and Task 1.2 depends on them being unchanged.

- [ ] **Step 3: Verify the pipeline still loads the skill**

Run: `cd apps/backend && uv run pytest tests/ -k "wiki" -v`
Expected: existing wiki tests pass. If `_writer_rules` asserts on skill structure, adapt
the skill edit rather than the assertion, and report that the assertion existed.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/app/modules/knowledge/skills/wiki-page-writer/SKILL.md
git commit -m "docs(skills): drop frontmatter template the pipeline overrides"
```

---

### Task 0.6: Phase 0 verification

- [ ] **Step 1: Run the full gate set**

```bash
cd apps/backend
uv run pytest tests/knowledge/ -v
uv run python -m tests.knowledge.okf_conformance_test || echo "EXPECTED FAIL: okf_version"
uv run --with pyyaml --no-project python vendor/okf_validate.py ../../openwiki --json
```
Expected: honesty tests pass except the version mismatch, which fails by design;
validator still reports `openwiki/` with 0 errors.

- [ ] **Step 2: Confirm no wiki output changed**

Run: `git diff --stat main -- openwiki/ knowledge/`
Expected: **empty**. Phase 0 must not have touched a single generated artifact. If it
did, revert that file — it belongs to Phase 1 or 2.

- [ ] **Step 3: Report and stop at Gate A**

---

# 🛑 GATE A — DECISION REQUIRED, STOP HERE

**Do not proceed. Report the following and wait for an explicit answer.**

### The question

Should a **machine** verification event be written into the concept's own frontmatter as
`verified: [{ by: process:<verifier>/<version>, at: <iso> }]`?

### Why it is not yours to decide

There is a real, documented tension:

- **For writing it in the bundle:** the verifier pass in `wiki_builder.py:358-365`
  rewrites pages in place, and the only trace it ran is a run log
  (`wiki_builder.py:389`) and the `--no-verify` flag (`:475`). Under `SPEC.md:405`,
  every concept in this repository is therefore `unverified` to any OKF consumer —
  including pages the verifier actually rewrote. The repo's central claim is measured
  assurance; the artifact currently carries less assurance than the pipeline delivers.
- **Against:** `apps/backend/tests/foundry/provenance_okf_test.py:20-25` and ADR-023
  deliberately keep `verified` **out** of the document and in the audit trail, because a
  document that can declare its own verifier can forge its own review.

### The distinction being proposed

Two different threat models, so both can be true at once:

| Verification kind | Actor | Where it lives | Why |
|---|---|---|---|
| Human sign-off | `human:<email>` | audit trail only (ADR-023, unchanged) | self-attested third-party claim; forgeable if in-document |
| Machine pass by our own pipeline | `process:<verifier>/<version>` | concept frontmatter | output of our tool, worth exactly what the fidelity gate over it is worth |

Nothing security-relevant hangs on this: OKF trust tiers are advisory and explicitly not
access control (`SPEC.md:410`), and no code in this repo reads a trust field for any
decision (audit §7 security note).

### What to report before asking

1. Whether `provenance_okf_test.py` and ADR-023 actually say what the audit reports.
   Quote the relevant lines.
2. Whether the verifier pass has a stable identity and version you can put in an actor
   string, or whether one must be introduced.
3. Whether `--no-verify` runs are distinguishable in the output today by any means.

### The three possible answers

- **A1 — Machine in bundle, human in trail** (what this plan assumes): proceed to Phase 1
  as written; add an ADR amending ADR-023 to record the split.
- **A2 — Nothing in the bundle**: skip Tasks 1.3 and 1.4; do Tasks 1.1, 1.2 and 1.5
  (`generated` only, which has no forgery argument against it since it names the
  producer, not a reviewer). Report the resulting bundle as permanently `unverified`.
- **A3 — Both in the bundle**: not recommended, contradicts ADR-023. If chosen, the ADR
  must be superseded first, and that is a separate plan.

**Wait for A1, A2 or A3.**

---

# PHASE 1 — Emit the trust family

**Precondition:** Gate A answered. If A2, skip Tasks 1.3–1.4.

**Rationale:** This is the phase with the actual value. The data mostly exists already
and is in the right shape — `manifest.json:12` carries `"openwiki/gpt-5.4"`, which is by
coincidence exactly the OKF `<producer>/<version>` actor convention, and `generatedAt`
(`:13`, written at `wiki_builder.py:408`) is already ISO with second precision in UTC.
This phase moves it from a bundle-level sidecar into the concepts, and adds the one
thing that genuinely does not exist: a record that verification happened.

---

### Task 1.1: Actor and timestamp helpers

**Files:**
- Create: `apps/backend/app/modules/okf/internal/actors.py`
- Test: `apps/backend/tests/okf/actors_test.py`

**Interfaces:**
- Produces:
  - `agent_actor(producer: str, version: str) -> str`
  - `process_actor(name: str, version: str | None = None) -> str`
  - `human_actor(identifier: str) -> str`
  - `okf_timestamp(moment: datetime | None = None) -> str`
  - `generated_block(by: str, at: str | None = None) -> dict[str, str]`
  - `verified_entry(by: str, at: str | None = None) -> dict[str, str]`
  Tasks 1.2, 1.3 and 2.1 consume these exact names.

- [ ] **Step 1: Confirm the module location matches the existing layout**

Run: `ls apps/backend/app/modules/okf/ apps/backend/app/modules/okf/internal/ 2>/dev/null`
Expected: an `okf` module with an `internal/` package (the audit cites
`okf/internal/catalog.py` and `okf/internal/migration.py`). If the layout differs, place
the file to match the real convention and report the deviation.

- [ ] **Step 2: Write the failing test**

Create `apps/backend/tests/okf/actors_test.py`:

```python
"""Actor strings and timestamps per OKF v0.2 §7 and §5.

SPEC.md:489-501 — <producer>/<version> for agents and tools, human:<id> for
people, process:<id> for automated processes. Trust tiers (SPEC.md:403-407)
key off the human: prefix, so a machine actor must never carry it.
SPEC.md:284-285 — every timestamp is ISO 8601 with an explicit UTC offset.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.okf.internal.actors import (
    agent_actor,
    generated_block,
    human_actor,
    okf_timestamp,
    process_actor,
    verified_entry,
)


def test_agent_actor_uses_producer_slash_version() -> None:
    assert agent_actor("openwiki", "0.4.0") == "openwiki/0.4.0"


def test_process_actor_carries_process_prefix() -> None:
    assert process_actor("wiki-verifier", "1") == "process:wiki-verifier/1"
    assert process_actor("wiki-verifier") == "process:wiki-verifier"


def test_human_actor_carries_human_prefix() -> None:
    assert human_actor("jefferson") == "human:jefferson"


@pytest.mark.parametrize("factory", [lambda: agent_actor("openwiki", "0.4.0"),
                                     lambda: process_actor("wiki-verifier", "1")])
def test_machine_actors_never_claim_human(factory) -> None:
    """A machine actor that starts with human: would forge a human review."""
    assert not factory().startswith("human:")


@pytest.mark.parametrize("bad", ["", "  ", "open/wiki", "openwiki/"])
def test_agent_actor_rejects_malformed_input(bad: str) -> None:
    with pytest.raises(ValueError):
        agent_actor(bad, "0.4.0") if "/" not in bad else agent_actor("openwiki", "")


def test_timestamp_is_iso_with_explicit_utc_offset() -> None:
    stamp = okf_timestamp(datetime(2026, 9, 2, 14, 30, 0, tzinfo=timezone.utc))
    assert stamp == "2026-09-02T14:30:00+00:00"
    assert stamp.endswith("+00:00")


def test_timestamp_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        okf_timestamp(datetime(2026, 9, 2, 14, 30, 0))


def test_timestamp_normalizes_other_offsets_to_utc() -> None:
    from datetime import timedelta
    recife = timezone(timedelta(hours=-3))
    stamp = okf_timestamp(datetime(2026, 9, 2, 11, 30, 0, tzinfo=recife))
    assert stamp == "2026-09-02T14:30:00+00:00"


def test_generated_block_shape() -> None:
    block = generated_block("openwiki/0.4.0", "2026-09-02T14:30:00+00:00")
    assert block == {"by": "openwiki/0.4.0", "at": "2026-09-02T14:30:00+00:00"}


def test_generated_block_requires_by() -> None:
    """SPEC.md:377 — by is REQUIRED within generated."""
    with pytest.raises(ValueError):
        generated_block("")


def test_verified_entry_shape() -> None:
    entry = verified_entry("process:wiki-verifier/1", "2026-09-02T14:31:00+00:00")
    assert entry == {"by": "process:wiki-verifier/1", "at": "2026-09-02T14:31:00+00:00"}
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd apps/backend && uv run pytest tests/okf/actors_test.py -v`
Expected: FAIL — `ModuleNotFoundError: app.modules.okf.internal.actors`.

- [ ] **Step 4: Write the implementation**

Create `apps/backend/app/modules/okf/internal/actors.py`:

```python
"""OKF v0.2 actor strings and timestamps.

SPEC.md:489-501 (actor convention), SPEC.md:284-285 (timestamps),
SPEC.md:366-380 (generated), SPEC.md:384-399 (verified).

Trust tiers are derived from the human: prefix (SPEC.md:403-407) and are
advisory signals, never access control (SPEC.md:410). Nothing in this module
may be used in an authorization decision.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = [
    "agent_actor",
    "process_actor",
    "human_actor",
    "okf_timestamp",
    "generated_block",
    "verified_entry",
]


def _require(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} must be a non-empty string")
    if "/" in cleaned or ":" in cleaned:
        raise ValueError(f"{field} must not contain '/' or ':': {value!r}")
    return cleaned


def agent_actor(producer: str, version: str) -> str:
    """An agent or tool: <producer>/<version>."""
    return f"{_require(producer, 'producer')}/{_require(version, 'version')}"


def process_actor(name: str, version: str | None = None) -> str:
    """An automated process: process:<id>, optionally versioned."""
    base = f"process:{_require(name, 'name')}"
    return f"{base}/{_require(version, 'version')}" if version is not None else base


def human_actor(identifier: str) -> str:
    """A person: human:<id>. Only for genuine human action."""
    return f"human:{_require(identifier, 'identifier')}"


def okf_timestamp(moment: datetime | None = None) -> str:
    """ISO 8601 in UTC with an explicit offset, second precision."""
    if moment is None:
        moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("naive datetime rejected; OKF requires an explicit UTC offset")
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def generated_block(by: str, at: str | None = None) -> dict[str, str]:
    """SPEC.md:377 — 'by' is required within generated."""
    if not (by or "").strip():
        raise ValueError("generated.by is required")
    return {"by": by.strip(), "at": at or okf_timestamp()}


def verified_entry(by: str, at: str | None = None) -> dict[str, str]:
    """One verification event. SPEC.md:384-399."""
    if not (by or "").strip():
        raise ValueError("verified[].by is required")
    return {"by": by.strip(), "at": at or okf_timestamp()}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd apps/backend && uv run pytest tests/okf/actors_test.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/app/modules/okf/internal/actors.py apps/backend/tests/okf/actors_test.py
git commit -m "feat(okf): add actor and timestamp helpers per SPEC v0.2 §5/§7"
```

---

### Task 1.2: Emit `generated` on every page the builder writes

**Files:**
- Modify: `apps/backend/app/modules/knowledge/internal/wiki_builder.py` (anchors: page
  prompt at `:354`, model resolution at `:303`, manifest write at `:408`)
- Test: `apps/backend/tests/knowledge/wiki_generated_frontmatter_test.py`

**Interfaces:**
- Consumes: `agent_actor`, `okf_timestamp`, `generated_block` from Task 1.1.
- Produces: every page file written by the builder starts with a frontmatter block
  containing at minimum `type` and `generated`. Task 1.3 appends `verified` to the same
  block; Task 2.1 relies on the block surviving the adapter.

**Design constraint:** the model must **not** author the frontmatter. The builder writes
it after the model returns prose. This keeps `type` and the actor out of reach of a
prompt, and is why Task 0.5 removed the skill's template instead of fixing it.

- [ ] **Step 1: Verify the anchors and find the page-write site**

Run:
```bash
sed -n '295,310p;345,360p;400,415p' apps/backend/app/modules/knowledge/internal/wiki_builder.py
grep -n "write_text\|def _page\|def build" apps/backend/app/modules/knowledge/internal/wiki_builder.py
```
Expected: `tenant_config().foundry_model` at ~`:303`; the `sem frontmatter VitePress`
instruction at ~`:354`; the manifest write at ~`:408`; one or more page `write_text`
calls. Record the exact function that writes a page — the next steps modify it.

- [ ] **Step 2: Write the failing test**

Create `apps/backend/tests/knowledge/wiki_generated_frontmatter_test.py`:

```python
"""Pages written by wiki_builder carry OKF generated provenance.

Closes gap G2 of the 2026-09-02 audit: no concept in any bundle carried
`generated`, so every page read as unverified AND unattributed to a producer.
"""

from __future__ import annotations

import yaml

from app.modules.knowledge.internal import wiki_builder


def _frontmatter(text: str) -> dict:
    assert text.startswith("---"), "page has no frontmatter block"
    _, _, rest = text.partition("---")
    block, sep, _ = rest.partition("\n---")
    assert sep, "frontmatter block is not terminated"
    return yaml.safe_load(block) or {}


def test_rendered_page_carries_type_and_generated() -> None:
    page = wiki_builder.render_page(
        body="## Overview\n\nSome prose citing `apps/backend/app/main.py`.\n",
        title="Backend entrypoint",
        description="How the FastAPI app is wired.",
        producer="foundry-wiki-builder",
        version="gpt-5-mini",
    )
    data = _frontmatter(page)
    assert data["type"], "SPEC.md:187 — type is the only always-required key"
    assert data["generated"]["by"] == "foundry-wiki-builder/gpt-5-mini"
    assert data["generated"]["at"].endswith("+00:00")


def test_generated_by_is_never_a_human_actor() -> None:
    page = wiki_builder.render_page(
        body="## X\n", title="X", description="d",
        producer="foundry-wiki-builder", version="gpt-5-mini",
    )
    assert not _frontmatter(page)["generated"]["by"].startswith("human:")


def test_body_is_preserved_verbatim_below_the_block() -> None:
    body = "## Overview\n\nExact prose.\n"
    page = wiki_builder.render_page(
        body=body, title="T", description="d",
        producer="p", version="v",
    )
    assert page.endswith(body)


def test_model_supplied_frontmatter_in_body_is_not_trusted() -> None:
    """If the model emits its own block, it must not become the page's frontmatter."""
    body = "---\ntype: Forged\ngenerated: {by: 'human:someone'}\n---\n\n## Real\n"
    page = wiki_builder.render_page(
        body=body, title="T", description="d",
        producer="foundry-wiki-builder", version="gpt-5-mini",
    )
    data = _frontmatter(page)
    assert data["type"] != "Forged"
    assert data["generated"]["by"] == "foundry-wiki-builder/gpt-5-mini"
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd apps/backend && uv run pytest tests/knowledge/wiki_generated_frontmatter_test.py -v`
Expected: FAIL — `render_page` does not exist.

- [ ] **Step 4: Implement `render_page` and route page writes through it**

In `wiki_builder.py`:

- Add `render_page(*, body: str, title: str, description: str, producer: str, version: str, type_: str = "Wiki Page") -> str`. It must:
  1. Strip any leading frontmatter block the model emitted from `body` before using it
     (the forgery test above).
  2. Build the frontmatter dict in this key order: `type`, `title`, `description`,
     `generated`.
  3. Serialize with `yaml.safe_dump(..., sort_keys=False, allow_unicode=True)`, wrap in
     `---` delimiters, and return `block + "\n" + cleaned_body`.
  4. Use `generated_block(agent_actor(producer, version))` from Task 1.1.
- Change the page-write site found in Step 1 to write `render_page(...)` output instead
  of raw model output. Source `producer` as a module constant
  (`"foundry-wiki-builder"`) and `version` from the same resolution used at `:303`.
- Leave the `:354` prompt instruction saying the model emits no frontmatter — it is now
  true *and* enforced, rather than contradicted.

- [ ] **Step 5: Run to verify it passes**

Run: `cd apps/backend && uv run pytest tests/knowledge/wiki_generated_frontmatter_test.py -v`
Expected: all PASS.

- [ ] **Step 6: Verify the fidelity gate still passes on a real regeneration**

Run: `cd apps/backend && uv run pytest tests/ -k "fidelity or wiki" -v`
Expected: PASS. The fidelity regex (`wiki_builder.py:98`) parses citations from prose;
adding a frontmatter block above the prose must not change its count. **If a fidelity
number moves, stop** — that means the block is being counted as content.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/app/modules/knowledge/internal/wiki_builder.py \
        apps/backend/tests/knowledge/wiki_generated_frontmatter_test.py
git commit -m "feat(okf): builder writes generated provenance into page frontmatter"
```

---

### Task 1.3: Record the verification pass as a `verified` event

**Precondition:** Gate A answered **A1**. If A2, skip to Task 1.5.

**Files:**
- Modify: `apps/backend/app/modules/knowledge/internal/wiki_builder.py` (verifier at
  `:358-365`, run log at `:389`, `--no-verify` at `:475`)
- Test: `apps/backend/tests/knowledge/wiki_verified_frontmatter_test.py`

**Interfaces:**
- Consumes: `render_page` (1.2), `process_actor`, `verified_entry` (1.1).
- Produces: pages that went through the verifier carry a `verified` list; pages that did
  not carry no `verified` key at all.

**Design constraint:** absence must remain absence. `SPEC.md:405` derives `unverified`
from a missing key, so a `--no-verify` run must emit **no** `verified` key — not an
empty list, not a null.

- [ ] **Step 1: Read the verifier and confirm it rewrites in place**

Run: `sed -n '355,395p;470,480p' apps/backend/app/modules/knowledge/internal/wiki_builder.py`
Expected: a second model pass that re-grounds claims and returns rewritten page text; a
log line containing `" (verificada)"`; a `--no-verify` CLI flag.

- [ ] **Step 2: Write the failing test**

Create `apps/backend/tests/knowledge/wiki_verified_frontmatter_test.py`:

```python
"""A verification pass leaves a record in the concept it verified.

Closes gap G3: the verifier rewrote pages in place and left no trace except a
run log, so a verified page was indistinguishable from an unverified one to any
OKF consumer (SPEC.md:401-407).
"""

from __future__ import annotations

import yaml

from app.modules.knowledge.internal import wiki_builder


def _frontmatter(text: str) -> dict:
    _, _, rest = text.partition("---")
    block, _, _ = rest.partition("\n---")
    return yaml.safe_load(block) or {}


def _page() -> str:
    return wiki_builder.render_page(
        body="## Overview\n\nProse citing `apps/backend/app/main.py`.\n",
        title="T", description="d",
        producer="foundry-wiki-builder", version="gpt-5-mini",
    )


def test_stamping_adds_a_verified_event() -> None:
    stamped = wiki_builder.stamp_verified(_page(), verifier="wiki-verifier", version="1")
    data = _frontmatter(stamped)
    assert data["verified"] == [
        {"by": "process:wiki-verifier/1", "at": data["verified"][0]["at"]}
    ]
    assert data["verified"][0]["at"].endswith("+00:00")


def test_verifier_is_a_process_actor_not_a_human() -> None:
    """ADR-023: human sign-off stays in the audit trail. A machine pass must
    never masquerade as one (SPEC.md:403-407)."""
    stamped = wiki_builder.stamp_verified(_page(), verifier="wiki-verifier", version="1")
    assert _frontmatter(stamped)["verified"][0]["by"].startswith("process:")


def test_unstamped_page_has_no_verified_key_at_all() -> None:
    """Absence is meaningful: SPEC.md:405 derives 'unverified' from a missing key."""
    assert "verified" not in _frontmatter(_page())


def test_stamping_twice_appends_rather_than_replaces() -> None:
    once = wiki_builder.stamp_verified(_page(), verifier="wiki-verifier", version="1")
    twice = wiki_builder.stamp_verified(once, verifier="fidelity-gate", version="1")
    entries = _frontmatter(twice)["verified"]
    assert [e["by"] for e in entries] == [
        "process:wiki-verifier/1", "process:fidelity-gate/1",
    ]


def test_stamping_preserves_generated_and_body() -> None:
    page = _page()
    stamped = wiki_builder.stamp_verified(page, verifier="wiki-verifier", version="1")
    assert _frontmatter(stamped)["generated"] == _frontmatter(page)["generated"]
    assert stamped.endswith("Prose citing `apps/backend/app/main.py`.\n")
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd apps/backend && uv run pytest tests/knowledge/wiki_verified_frontmatter_test.py -v`
Expected: FAIL — `stamp_verified` does not exist.

- [ ] **Step 4: Implement `stamp_verified` and call it from the verifier**

In `wiki_builder.py`:

- Add `stamp_verified(page: str, *, verifier: str, version: str | None = None) -> str`.
  It parses the existing frontmatter, appends `verified_entry(process_actor(verifier,
  version))` to a `verified` list (creating the list if absent), re-serializes with the
  same `sort_keys=False` settings, and returns the page with its body untouched.
- Call it at the point the verifier's rewritten page is accepted (`:358-365`), on the
  verified text, before it is written.
- Ensure the `--no-verify` path (`:475`) never calls it.
- Keep the existing `" (verificada)"` log line. It is now redundant with the artifact,
  which is the point.

- [ ] **Step 5: Run to verify it passes**

Run: `cd apps/backend && uv run pytest tests/knowledge/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/app/modules/knowledge/internal/wiki_builder.py \
        apps/backend/tests/knowledge/wiki_verified_frontmatter_test.py
git commit -m "feat(okf): verifier pass stamps a process: verified event on the page"
```

---

### Task 1.4: Amend ADR-023 to record the split

**Precondition:** Gate A answered **A1**.

**Files:**
- Create: `docs/adr/ADR-034-okf-machine-verification-in-bundle.md`
- Modify: `docs/adr/README.md` (the ADR index)
- Modify: `docs/adr/ADR-023-*.md` (add a "Amended by ADR-034" line; do not rewrite it)

- [ ] **Step 1: Read ADR-023 and confirm its stated reasoning**

Run: `ls docs/adr/ | grep 023 && cat docs/adr/ADR-023-*.md`
Expected: a decision keeping `verified` in the audit trail, with a forgery rationale. If
the rationale differs from what Gate A described, **stop and report** — the ADR is the
authority, not this plan.

- [ ] **Step 2: Write ADR-034**

Follow the format of the existing ADRs in that directory. Content must state:
- **Context:** OKF v0.2 §5.2 makes `generated` and `verified` first-class; the wiki
  verifier left no trace in the artifact (audit gap G3).
- **Decision:** machine verification by this repository's own pipeline is recorded in
  concept frontmatter as `process:<name>/<version>`; human sign-off remains in the audit
  trail per ADR-023, unamended in substance.
- **Rationale:** different threat models — a document declaring its own *human* reviewer
  is self-attestation by a party we do not control; a document recording that *our*
  verifier ran is our tool's output, worth what the fidelity gate over it is worth.
- **Consequences:** OKF consumers see `machine-confirmed` (`SPEC.md:405`) rather than
  `unverified` for verified pages; no trust field is read for any authorization decision
  (`SPEC.md:410`), and none may become one.
- **Status:** accepted; amends ADR-023.

- [ ] **Step 3: Update the ADR index and the count**

Add ADR-034 to `docs/adr/README.md`. Re-check the range string in `CLAUDE.md` fixed in
Task 0.4 and update it if 034 now extends it.

- [ ] **Step 4: Commit**

```bash
git add docs/adr/
git commit -m "docs(adr): ADR-034 machine verification in bundle, human in trail"
```

---

### Task 1.5: Declare `okf_version: "0.2"` and close the gate failure

**Precondition:** Tasks 1.2 (and 1.3 unless A2) complete, and the `openwiki/` bundle
regenerated so its pages carry `generated`.

**Files:**
- Modify: `openwiki/index.md:2`
- Read only: `apps/backend/tests/knowledge/okf_conformance_test.py`

**Rationale:** ordered last on purpose. Declaring v0.2 on a bundle carrying no v0.2
fields would be the same false claim Phase 0 removed, pointed the other way. The
declaration follows the content.

- [ ] **Step 1: Confirm the bundle now carries v0.2 fields**

Run:
```bash
grep -L "^generated:" openwiki/**/*.md 2>/dev/null | grep -v index.md | grep -v log.md
```
Expected: **no output** — every non-reserved page has `generated`. If files are listed,
they were not regenerated; regenerate before proceeding.

- [ ] **Step 2: Change the declaration**

Set `okf_version: "0.2"` in `openwiki/index.md`. Change nothing else in that file —
`SPEC.md:512-513` permits only this key there.

- [ ] **Step 3: Run the gate**

```bash
cd apps/backend
uv run --with pyyaml --no-project python vendor/okf_validate.py ../../openwiki --json
uv run python -m tests.knowledge.okf_conformance_test
uv run pytest tests/knowledge/ -v
```
Expected: validator reports 0 errors and no `okf_version` warning; the gate now **exits
zero** for the first time since Task 0.1; honesty tests pass.

- [ ] **Step 4: Update the findings document**

In `docs/OKF-CONFORMANCE-FINDINGS.md`, mark §7 defect 2 and gaps G2 and G3 (G3 only if
A1) as closed, naming the commits. Leave the rest of the report as the historical record
— do not retroactively edit its measurements.

- [ ] **Step 5: Commit**

```bash
git add openwiki/index.md openwiki/ docs/OKF-CONFORMANCE-FINDINGS.md
git commit -m "feat(okf): declare okf_version 0.2 now that the bundle carries v0.2 fields"
```

---

### Task 1.6: Phase 1 verification, then stop at Gate B

- [ ] **Step 1: Full verification**

```bash
cd apps/backend
uv run pytest tests/ -v
uv run python -m tests.knowledge.okf_conformance_test
uv run python -m eval.wiki_shelf_test
```
Expected: everything green.

- [ ] **Step 2: Confirm no access-control surface moved**

Run: `git diff main -- apps/backend/app/modules/knowledge/internal/frontmatter.py apps/backend/app/modules/knowledge/internal/ingest.py`
Expected: **empty for `frontmatter.py`.** Any diff there violates a global constraint —
revert it.

- [ ] **Step 3: Report and stop at Gate B**

---

# 🛑 GATE B — HYPOTHESIS TEST, STOP HERE

**Phase 2 cannot be designed until this is answered. Investigate, report, and wait.**

### The question

Does `docbundle.schema.json` actually govern the **content of the pages**, or only the
`manifest.json`?

### Why it matters

`adapt_openwiki.py:26-38` justifies stripping frontmatter from every page by saying the
docbundle contract must stay byte-identical to its origin project, and proposes a
sidecar file next to the manifest as the workaround. If that contract governs only the
manifest, then pages may keep their frontmatter, no sidecar is needed, and Q1 of the
audit dissolves. If it governs page content too, Phase 2 needs a different design and
possibly an agreement with the origin project's owner.

Evidence that it may only govern the manifest: the ingest path **already** parses
frontmatter for the corpus (`ingest.py:167` via `frontmatter.py`), so the machinery
handles it.

### What to determine and report

1. Read `apps/backend/app/modules/knowledge/docbundle.schema.json` in full. Does any
   property constrain page file content, or only `manifest.json` structure?
2. Read `adapt_openwiki.py:22-38` and `adapt_deepwiki.py`. Is the stripping required by
   the schema, or a convention that grew alongside it?
3. Read `ingest_docbundles.py` around `:637`. Does it read page bytes verbatim, or parse
   them? Would a leading frontmatter block change any offset, hash, or chunk boundary?
4. Does anything downstream hash or byte-compare page content (dedup, change detection,
   `.last-update.json`)?
5. Who owns the schema, and is a sidecar already agreed anywhere in `docs/`?

### The two branches

- **B1 — the schema governs only the manifest:** Phase 2 proceeds as sketched below.
  `adapt_openwiki.py` stops stripping; pages keep frontmatter; `wiki-bundle` joins the
  gate list; frontmatter fields are projected into the search index.
- **B2 — the schema governs page content:** Phase 2 as sketched is **wrong**. Stop and
  report; the alternatives (sidecar provenance file; a second bundle format; negotiating
  the contract) are a design decision requiring brainstorming, not this plan.

**Wait for B1 or B2.**

---

# PHASE 2 — Preserve frontmatter, then use it (SKETCH — requires Gate B = B1)

**This phase is deliberately a sketch, not executable steps.** Its design depends on
Gate B's answer, and writing bite-sized steps for it now would be inventing detail about
files whose constraints are unknown. After Gate B returns B1, this section gets rewritten
into full tasks in the same format as Phases 0 and 1.

**Rationale for the ordering:** this is the only phase with a measurable runtime payoff —
deterministic pre-filtering before agentic retrieval, which the OpenWiki team's stated
motivation and the audit both identify as the reason structured metadata is worth
carrying. It is also the only reason §11 conformance of `wiki-bundle/` matters at all:
today the index reads body text only (`retrieval.py:317` selects `snippet,blob_url`), so
conformance there changes no answer.

### Sketched tasks

**2.1 — Stop stripping.** `adapt_openwiki.py:22-24` preserves the frontmatter block
instead of discarding it. Test: a fixture page with frontmatter survives the adapter
byte-identically in its block.

**2.2 — Add `wiki-bundle` to the gate.** Move
`knowledge/wiki-bundle/foundry-assured/v0.20260819` from `EXCLUDED_BUNDLES` (Task 0.2)
into `BUNDLES`. This is the task that closes audit defect 1. It will fail until 2.1 lands
and the bundle is regenerated — that ordering is the point.

**2.3 — Project `type`, `tags`, `status` into the search index.** Schema change plus
re-ingest. Requires an index rebuild; sequence with `acl_setup.py` deliberately.

**2.4 — Deterministic pre-filter, ANDed with `permissionFilter`.** The security-critical
task. Tests must include a caller who is entitled to nothing, verifying that adding a
`type` filter cannot widen their result set. **A filter that replaces rather than
intersects `permissionFilter` (`acl_setup.py:125`) is a security defect, not a bug.**

**2.5 — Measure.** Before/after on latency and tokens for a fixed question set, so the
phase's justification is a number and not an assumption. If the number does not move,
that is a finding worth recording, not a failure to hide.

---

# Explicitly NOT in this plan

Recorded so a later reader knows these were considered and declined, not forgotten.

- **`log.md` generation (audit G4, Q3).** Optional per `SPEC.md:535`. OpenWiki does not
  generate one either (audit drift D4), so adopting OpenWiki would not supply it. Git
  history plus the manifest already cover the need. Prompt surface without a buyer.
- **`sources[]` with footnote-keyed per-claim attribution (G7).** Wait until line-ranged
  citations are actually gated. Today `_CITE_RE` (`wiki_builder.py:98`) makes `:line`
  optional and 0 of 676 citations in the ingested bundle carry one. Formalizing
  provenance for a citation format you measure but do not enforce standardizes an empty
  set. Revisit if the fidelity gate starts requiring line ranges.
- **`stale_after` and `status` on generated pages (G8).** Freshness is tracked outside
  the documents today (`openwiki/.last-update.json`,
  `apps/backend/eval/wiki_freshness_test.py`) and that works. Moving it in is a
  preference, not a gap.
- **`Attested Computation` (G9).** The attester half maps onto the eval gates; the
  executor and receipt halves do not exist. Building them is a product decision about
  publishing the assurance mechanism to third parties, not an OKF conformance task.
- **`docs/` conformance.** The 60 §11.1 errors there are measured against a different
  contract (`DOCS-STANDARD.md`). Not an OKF finding. Only the one unparseable block
  (Task 0.3) is in scope, because it would crash ingest.
- **Adopting OpenWiki as the pipeline.** Independent decision (audit Q2). Three producers
  exist and the fidelity gate is producer-agnostic by construction. Worth a throwaway-clone
  trial of a newer CLI (audit Q6) since its dogfooded wiki already emits
  `generated: { by: "openwiki/0.4.0", ... }` — but that is a spike, not this plan.

---

# Flagged separately: the dormant `groups:` path

**Not part of this plan. Raise it, do not touch it.**

`frontmatter.py:60` reads a `groups:` key that becomes the Azure AI Search
`permissionFilter` (`ingest.py:167-177`, `acl_setup.py:125`, ADR-031). It is fail-closed
in both directions and correctly designed. But `grep -rn "^groups:"` across every `.md`
returns nothing, while live ACLs come from a gitignored `ACL_CLASSIFICATION` JSON
(`acl_setup.py:71-77`).

Security-relevant code that no committed content exercises rots: nobody tests the path,
and it wakes up on some future deploy. Either exercise it with a fixture or remove it.
This is independent of OKF and plausibly more urgent than half of Phase 2 — it deserves
its own brainstorm, not a task here.

---

# Rollback

Each phase is independently revertible.

- **Phase 0:** revert the commits. No generated artifact changed (Task 0.6 Step 2
  asserts this), so nothing needs regenerating.
- **Phase 1:** revert the commits, then regenerate the affected bundles. Pages will lose
  their frontmatter blocks; the validator will still report 0 errors for `openwiki/`
  only if `okf_version` is reverted to `"0.1"` in the same change — revert Task 1.5 and
  Task 0.1 together or the gate stays red.
- **Phase 2:** the search index change (2.3) is the only one requiring an operational
  step to undo — an index rebuild. Sequence it last for that reason.

---

# Definition of done

Phase 0 and Phase 1 are complete when all of the following hold:

- [ ] `uv run python -m tests.knowledge.okf_conformance_test` exits **zero** and its
      output names both the bundles it checked and the ones it excluded, with reasons.
- [ ] Every non-reserved page in `openwiki/` carries `type` and `generated`, and
      `generated.by` matches `<producer>/<version>` with no `human:` prefix anywhere.
- [ ] (A1 only) Pages the verifier rewrote carry a `process:` `verified` entry; pages
      from a `--no-verify` run carry **no** `verified` key.
- [ ] `openwiki/index.md` declares `okf_version: "0.2"` and the validator emits no
      version warning.
- [ ] `git diff main -- apps/backend/app/modules/knowledge/internal/frontmatter.py` is
      empty.
- [ ] Every fidelity and freshness gate that passed before still passes, with unchanged
      numbers.
- [ ] `docs/OKF-CONFORMANCE-FINDINGS.md` records which gaps closed and by which commit,
      with its original measurements left intact.
- [ ] Gate B has been investigated and answered, even if Phase 2 is not started.
