# OKF v0.2 Adoption Implementation Plan (rev. 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Create an isolated workspace first via `superpowers:using-git-worktrees`. Do not start on `main`.

**Goal:** Make every wiki artifact this repository publishes carry OKF v0.2 trust metadata (`generated`, `verified`), stop discarding that metadata on the path to the knowledge base, and make the conformance gate report only what it measured.

**Architecture:** Four phases, ordered so **CI is green after every task** but one. Phase 0 repairs claims the repo makes that are false. Phase 1 adds the OKF primitives and makes the gate name its blind spots. Phase 2 makes *our own* producer, `wiki_builder.py`, emit the trust family. Phase 3 preserves frontmatter into the ingested bundle while keeping YAML out of the retrieval corpus. Phase 4 then runs the external generator **once** — it emits v0.2 by itself — so `openwiki/` and `knowledge/wiki-bundle/` both come back correct in a single pull request, and every gate is tightened against that output. One decision remains at the end: Gate C.

**Tech Stack:** Python 3.12 · `uv` · FastAPI · Azure AI Search · Foundry Agent Framework · GitHub Actions · `import-linter`.

---

## What changed from the 2026-09-02 draft, and why

This revision supersedes `docs/2026-09-02-okf-v02-adoption.md`. That draft was written
from `docs/OKF-CONFORMANCE-FINDINGS.md` without reading the source; six of its assumptions
do not hold. Each correction below was verified against the file named.

| # | Draft assumed | Verified reality | Effect on this plan |
|---|---|---|---|
| 1 | `wiki_builder.py` produces `openwiki/`, so Phase 1 code makes Task 1.5 reachable | `openwiki/` is written by the **external OpenWiki CLI**, pinned at `openwiki@0.4.3` (`.github/workflows/wiki-regen.yml:81`). `wiki_builder.py:399` writes only `knowledge/wiki-bundle/<component>/<version>/pages/`. | Split into **Phase 2** (our producer, `wiki-bundle`) and **Phase 4** (their producer, `openwiki/`). The draft's circular dependency is gone. |
| 2 | Whether OpenWiki ≥0.4 emits `generated` is an open spike (audit Q6) | Already answered **in the repo**: `wiki-regen.yml:68-81` records, measured 2026-08-27, that 0.4.3 emits OKF v0.2 and that `adapt_openwiki.py` digests `generated{by,at}/verified/sources` cleanly. The committed `openwiki/` is stale 0.3.x output (`openwiki/.last-update.json`: 2026-08-19). | Gaps G2 and G5 for `openwiki/` close by **running an existing workflow**, not by writing code. Task 3.1. |
| 3 | The gate should be made strict first (Task 0.1), leaving CI red until Task 1.5 | Nothing in the draft could turn it green again. | Strictness moved to **Task 4.2**, after the regeneration that satisfies it. CI goes red in exactly one place, by design, and the next task closes it. |
| 4 | Tests are pytest files run with `uv run pytest` | `.github/workflows/ci.yml` contains **zero** `pytest` invocations; every gate is an executable module with `main()` returning an exit code (`CLAUDE.md`, "Gates"). `scripts/gates.py` derives the list from `ci.yml`. A pytest file gates nothing. | Every test in this plan is an executable module **and is registered in `ci.yml`** in the same task. |
| 5 | Test helpers may use `Path(__file__).resolve().parents[3]` | `tests/architecture/filesystem_anchors_test.py:34` scans `tests/` and forbids `parents[N]` with N > 1. | All paths anchor on the `app` package, copying `tests/knowledge/okf_conformance_test.py:34-35` verbatim. |
| 6 | `wiki_builder` may import `app.modules.okf.internal.actors` | `importlinter.toml:119` puts `app.modules.okf` under a per-module "internals are private" contract, and `tests/architecture/module_graph.json` pins the exact inter-module edge set. | Imports go through `app.modules.okf.public`, `public.py` re-exports, and the new `knowledge → okf` edge is re-recorded. Task 2.1. |

Two further corrections, smaller:

- **`BUNDLES` already exists** as a module-level `dict[str, Path]` (`okf_conformance_test.py:40`). The draft's "lift it into a constant" step was a no-op, and its `_gated_bundles()` iterated the dict's *keys*, resolving `agents/assured/flows` against the repo root when it lives under `apps/backend/` — the honesty test would have checked directories that do not exist and passed vacuously.
- **ADR-034 is taken** (`.smart-coding/_adrs/ADR-034-authoring-area-and-git-first-publication.md`). This plan uses **ADR-035**.

### Gate B is closed — answered B1, with a caveat the draft did not anticipate

The draft halted at Gate B to ask whether `docbundle.schema.json` governs page content.
It does not, and the question is settled here rather than re-asked:

- The schema (`apps/backend/app/modules/knowledge/internal/docbundle.schema.json` — note
  `internal/`; the draft's path was wrong) declares 13 properties, all of them
  `manifest.json` fields. It contains **zero** occurrences of `content`, `body`,
  `frontmatter`, `markdown` or `hash`.
- Page bytes are already not preserved: `ingest_docbundles.py:249-256` reads the page,
  drops a leading `# ` H1, prepends `f"# {label} — {title}\n\n"` and uploads *that*.
  Nothing hashes or byte-compares page content.

**The caveat:** the reason `adapt_openwiki.py:22-24` strips frontmatter was never the
schema — it is that the page body *is* the indexed text, and YAML in the body would enter
the retrieval corpus (the same reason stated at `ingest.py:137-142` for the corpus path).
So "stop stripping" is only half a design. Phase 3 preserves frontmatter **in the file**
and strips it **at index time**, which is why Task 3.1 and Task 3.2 are inseparable and
land in that order. Audit Q1 dissolves: no sidecar file is needed.

---

## Decisions recorded, 2026-09-02

The four choices that were the repository owner's to make, asked formally and answered
before execution. They are settled; an implementer does not reopen them.

| Decision | Answer | Where it lands |
|---|---|---|
| **Gate A** — machine `verified` in our own bundle | **A1** — machine in the bundle, human sign-off out of it | Tasks 2.2 and 2.3; full reasoning and the ADR-023 correction at the Gate A section below |
| **Verifier actor form** | `process:wiki-verifier/<model deployment>` — `process:<id>` per `SPEC.md:497`, versioned by the deployment that actually ran | `_VERIFIER` constant, Task 2.2 |
| **`type` on pages our builder writes** | `reference` — the spec's own example value (`SPEC.md:180`) and `DOCS-STANDARD.md`'s vocabulary | `_PAGE_TYPE` constant, Task 2.1 |
| **When to dispatch `wiki-regen.yml`** | **Once, at the end** | Phase 4, after every code change is in place |

Two consequences worth stating, because they are the cost of those answers rather than
bugs to discover later:

- **`type` vocabularies will differ.** OpenWiki writes `concept`/`guide` per page into
  `openwiki/`, chosen by its model; ours writes a constant `reference`. After Task 3.1 the
  adapter preserves whatever the source page declared, so `knowledge/wiki-bundle/` carries
  OpenWiki's values and only pages from `wiki_builder` carry ours. `SPEC.md:182-186` makes
  both conformant. It starts to matter only at Gate C, if `type` becomes a filter facet.
- **A single dispatch reordered the plan.** Phases 3 and 4 are swapped relative to the
  first draft: frontmatter preservation lands *before* the regeneration, so one run
  produces a correct `openwiki/` and a correct `knowledge/wiki-bundle/` in the same pull
  request. This is what removes the second dispatch the draft would have needed.

---

## Base branch — verified, not assumed

This plan **cannot** be based on `main`. `main` does not contain
`apps/backend/app/modules/okf/`, `apps/backend/vendor/okf_validate.py`, or
`apps/backend/tests/knowledge/okf_conformance_test.py` — every phase depends on them, and
they exist only on `feat/wizard-decisao-com-contexto`, which is 43 commits ahead.

Base: **`feat/okf-v02-adoption`, branched from `feat/wizard-decisao-com-contexto` @
`54975e0`**, in an isolated worktree at `/Users/jefferson.barnabe/projects/foundry-okf`.
Baseline verified before the first task: `scripts/gates.py` → **107/107 green** (after
`uv sync` in both `apps/backend` and `apps/mcp` — `apps/mcp` is a separate `uv` project and
an unsynced one fails 19 gates with `ModuleNotFoundError`, which is environment, not
regression).

The pull request stacks on the wizard branch's. If that branch merges to `main` first,
rebase before opening this one.

---

## Global Constraints

- **Do not touch access control.** No frontmatter field may gain influence over an
  authorization decision. OKF trust tiers are advisory and explicitly not access control
  (`SPEC.md:410`). The `groups:` path (`frontmatter.py:60`, `ingest.py:167-177`, ADR-031)
  must end this plan byte-identical.
- **Any search filter is ANDed with `permissionFilter`, never substituted for it**
  (`acl_setup.py:125`). Out of scope here; stated so Gate C inherits it.
- **`docbundle.schema.json` is a vendored contract. Do not modify it.** Phase 4 does not
  need to.
- **Tests are executable modules, not pytest.** Every test file exposes `main() -> int`
  and ends with `sys.exit(main())`. Copy the shape of
  `apps/backend/tests/foundry/provenance_okf_test.py:53-59` (a local `check(nome, cond)`
  appending to `falhas`).
- **A test that is not in `.github/workflows/ci.yml` gates nothing.** Every task that adds
  a test adds its `ci.yml` entry in the same commit. `scripts/gates.py` derives the local
  run from that file.
- **Never compute a path with `parents[N]`, N > 1, from `__file__`.** Anchor on the `app`
  package. The sanctioned form, copied verbatim from
  `apps/backend/tests/knowledge/okf_conformance_test.py:32-35`:
  ```python
  import app as _app
  BACKEND = Path(_app.__file__).resolve().parent.parent
  REPO = BACKEND.parents[1]
  ```
  Gate: `uv run python -m tests.architecture.filesystem_anchors_test`.
- **Cross-module imports go through `public.py` only** (ADR-017). Gate:
  `uv run lint-imports --config importlinter.toml`. A new inter-module edge must be
  re-recorded: `uv run python -m tests.architecture.module_graph_test --update`.
- **OKF version targeted: v0.2**, per `SPEC.md:3` at commit
  `ad30107c31c06aec8a7d5636e0d1058118604e6f`.
- **Actor convention is normative** (`SPEC.md:489-501`): `<producer>/<version>` for agents
  and tools, `human:<id>` for people, `process:<id>` for automated processes. Trust tiers
  key off the `human:` prefix, so a machine actor must never carry it.
- **All timestamps are ISO 8601 with an explicit UTC offset** (`SPEC.md:284-285`). A bare
  date is not conformant.
- **Do not add a dependency.** Everything here uses `pyyaml` and the stdlib.
- **`apps/backend/vendor/okf_validate.py` is read-only** third-party code
  (`vendor/README.md:11-14`). A needed behavior change is a finding to report, not an edit.
- **Every command is worktree-relative.** Commands say `cd "$(git rev-parse --show-toplevel)"`,
  never an absolute path. This plan was drafted in one worktree and is executed in another;
  an absolute path to the drafting worktree resolves to a real checkout of a DIFFERENT
  branch, where a verification passes while telling you nothing about your work. Found in
  execution, after 13 such paths had been written.
- **Commit after every task**, Conventional Commits, scope `okf`, `knowledge` or `docs`.
- **CI must be green after every task**, with exactly one carved exception: Task 3.1
  ends red and Task 3.2 closes it. They are two commits on one branch and one pull
  request. Any other task that leaves a gate red is wrong.

---

## File Structure

| Path | Created / Modified | Responsibility |
|---|---|---|
| `apps/backend/app/modules/okf/internal/actors.py` | create | OKF actor strings and timestamps. Pure, no I/O, no imports outside stdlib. |
| `apps/backend/app/modules/okf/public.py` | modify | Re-export the actor helpers so other modules may use them. |
| `apps/backend/tests/okf/actors_test.py` | create | Gate for the above. |
| `apps/backend/tests/knowledge/frontmatter_parseavel_test.py` | create | Every `.md` under `docs/` that looks like it has frontmatter must actually parse. |
| `apps/backend/tests/knowledge/okf_conformance_test.py` | modify | Names its exclusions (Task 1.2); treats an `okf_version` mismatch as an error (Task 3.2); gains `wiki-bundle` (Task 4.3). |
| `apps/backend/app/modules/knowledge/internal/wiki_builder.py` | modify | `render_page` / `stamp_verified`; page writes route through them. |
| `apps/backend/tests/knowledge/wiki_frontmatter_test.py` | create | Gate for `render_page` and `stamp_verified`. |
| `apps/backend/app/modules/knowledge/internal/adapt_openwiki.py` | modify | Stops discarding the frontmatter block. |
| `apps/backend/app/modules/knowledge/internal/ingest_docbundles.py` | modify | Strips frontmatter at index time so YAML never enters retrieval. |
| `apps/backend/tests/knowledge/bundle_frontmatter_roundtrip_test.py` | create | Gate for the preserve-then-strip pair. |
| `apps/backend/tests/architecture/module_graph.json` | modify | Re-record the new `knowledge → okf` edge. |
| `.github/workflows/ci.yml` | modify | Register each new gate. |
| `docs/adr/ADR-035-okf-machine-verification-in-bundle.md` | create | Records the Gate A decision. `ADR-023-evidence-layer.md` is **not** modified — see Task 2.3. |

---

# PHASE 0 — Repairs that stand on their own

No design decisions, no artifact changes, CI green throughout.

---

### Task 0.1: Make an unparseable frontmatter block impossible to miss

**Files:**
- Create: `apps/backend/tests/knowledge/frontmatter_parseavel_test.py`
- Modify: `docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md` (line 3)
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: a CI gate asserting every `docs/**/*.md` opening with `---` has a YAML block
  that `yaml.safe_load` accepts. No later task depends on it; it prevents a class of bug
  that `ingest.py:162-165` turns into a hard exit.

**Rationale:** the `description` value contains `API oficial: 23 operações` — a `: ` inside
an unquoted YAML scalar. `yaml.safe_load` raises `mapping values are not allowed here`.
A naive `startswith("---")` check counts the file as having frontmatter, which is how it
survived; the vendored validator counts it as one of the 60 §11.1 errors under `docs/`.

- [ ] **Step 1: Confirm the failure mode**

Run:
```bash
cd apps/backend && uv run --with pyyaml --no-project python -c "
import re, yaml, pathlib
p = pathlib.Path('../../docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md')
m = re.match(r'\A---\r?\n(.*?)\r?\n---\r?\n', p.read_text(encoding='utf-8'), re.S)
print('block matched:', bool(m))
try:
    yaml.safe_load(m.group(1)); print('PARSES — finding is stale, stop and report')
except yaml.YAMLError as e:
    print('RAISES:', str(e).splitlines()[0])
"
```
Expected: `block matched: True` then `RAISES: mapping values are not allowed here`.
If it prints `PARSES`, stop and report — the finding is stale and this task is void.

- [ ] **Step 2: Write the failing gate**

Create `apps/backend/tests/knowledge/frontmatter_parseavel_test.py`. A varredura de `docs/` só exercita o caminho feliz depois que o repositório está limpo; os três ramos de erro da classificação ficariam sem cobertura se testados apenas contra arquivos reais. Por isso a classificação é uma função pura testada contra entradas sintéticas, e a varredura corre depois que a lógica é verificada.

```python
"""Um arquivo que PARECE ter frontmatter precisa ter frontmatter que parseia.

POR QUE ISTO É UM GATE E NÃO UMA CONVENÇÃO. `ingest.py:162-165` sai com erro num bloco
torto — de propósito, porque um YAML quebrado tornaria "declarei acesso errado"
indistinguível de "não declarei acesso" (ver `frontmatter.py:41-49`). Mas `docs/` nunca é
ingerido, então um bloco quebrado lá não tem sintoma nenhum: `startswith("---")` conta o
arquivo como tendo frontmatter, e todo mundo que só olha a primeira linha concorda.

Foi assim que `2026-08-17-user-managed-agents-and-knowledge-design.md` passou meses com um
`: ` dentro de escalar não citado. Este gate mede o que o parser mede, não o que o olho vê.

CONTEÚDO ESTÁ FORA DE ESCOPO. Não se cobra `type`, nem `title`, nem conformidade OKF — a
regra de `docs/` é a do `DOCS-STANDARD.md`, não a do OKF. Só se cobra que o YAML parseie.

A classificação é pura e testada contra entradas sintéticas, porque após o repositório estar
limpo uma varredura só exercita o caminho feliz. Ramos de erro sem teste em `docs/` ficariam
sem cobertura, e um gate cujos ramos de erro nunca rodam é o defeito que a auditoria de
2026-09-02 mediu.

    uv run python -m tests.knowledge.frontmatter_parseavel_test
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

import app as _app

BACKEND = Path(_app.__file__).resolve().parent.parent
REPO = BACKEND.parents[1]

#: `\A---\n … \n---` — o mesmo recorte de `knowledge/internal/frontmatter.py:26`, para que
#: este gate e o parser de produção discordem sobre zero arquivos.
BLOCO = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def _problema(texto: str) -> str | None:
    """A descrição do problema no bloco de frontmatter, ou None se não há problema.

    Pura e separada do loop porque é o que se consegue testar. Varrer `docs/` só
    exercita o caminho feliz depois que o repositório está limpo — os três ramos de
    erro ficariam sem cobertura nenhuma, e um gate cujos ramos de erro nunca rodam
    é o defeito que a auditoria de 2026-09-02 mediu, não a defesa contra ele.
    """
    if not texto.startswith("---"):
        return None  # sem bloco não é erro aqui; frontmatter em docs/ é opcional

    m = BLOCO.match(texto)
    if not m:
        return "bloco `---` aberto e não fechado"

    try:
        dados = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        return str(exc).splitlines()[0]

    if dados is not None and not isinstance(dados, dict):
        return f"frontmatter não é um mapa, e sim {type(dados).__name__}"

    return None


def main() -> int:
    falhas: list[str] = []

    # Testes sintéticos — cobrem os cinco ramos da classificação.
    def check(nome: str, cond: bool) -> None:
        if not cond:
            falhas.append(f"[lógica] {nome}")

    # Ramo 1: texto sem `---` inicial → None
    check("sem --- inicial", _problema("# Heading\nconteúdo") is None)

    # Ramo 2: bloco bem-formado que parseia para um mapa → None
    check("bloco válido e mapa", _problema("---\ntitle: Teste\n---\nconteúdo") is None)

    # Ramo 3: bloco que abre e não fecha → erro não-None
    check(
        "bloco não fechado",
        _problema("---\ntitle: Teste\nconteúdo") is not None,
    )

    # Ramo 4: bloco cujo YAML levanta exceção (`: ` unquoted)
    check(
        "YAML com erro de sintaxe",
        _problema("---\ndescription: API oficial: 23 operações\n---\nconteúdo")
        is not None,
    )

    # Ramo 5: bloco que parseia para não-mapa (lista YAML)
    check(
        "YAML que não é mapa",
        _problema("---\n- item1\n- item2\n---\nconteúdo") is not None,
    )

    # Falhas na lógica sinalizadas em primeiro lugar.
    if falhas:
        for f in falhas:
            print(f"  ✗ {f}")
        print(
            f"\n❌ {len(falhas)} ramo(s) da lógica de classificação falhou(aram)."
        )
        return 1

    # Varredura de `docs/` contra a lógica testada.
    for md in sorted((REPO / "docs").rglob("*.md")):
        texto = md.read_text(encoding="utf-8", errors="replace")
        problema = _problema(texto)
        if problema:
            rel = md.relative_to(REPO)
            falhas.append(f"{rel}: {problema}")

    for f in falhas:
        print(f"  ✗ {f}")
    if falhas:
        print(f"\n❌ {len(falhas)} bloco(s) de frontmatter não parseiam.")
        print("   Valor com `: ` precisa de aspas. `ingest.py:162-165` sai com erro num destes.")
        return 1
    print("✅ todo bloco de frontmatter em docs/ parseia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run it and confirm it fails**

Run:
```bash
cd apps/backend && uv run python -m tests.knowledge.frontmatter_parseavel_test
```
Expected: exit 1, one line naming
`docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md`.
If it names other files, fix those in Step 4 as well.

- [ ] **Step 4: Quote the value**

In `docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md`, wrap
the `description` value in double quotes so the embedded `: ` is literal. Change nothing
else — not the wording, not the other keys, not the line count.

- [ ] **Step 5: Confirm it passes**

Run: `cd apps/backend && uv run python -m tests.knowledge.frontmatter_parseavel_test`
Expected: exit 0, `✅ todo bloco de frontmatter em docs/ parseia.`

- [ ] **Step 6: Register the gate in CI**

In `.github/workflows/ci.yml`, in the `backend` job, immediately after the line
`run: uv run python -m tests.okf.changeset_test`, add:

```yaml
      # Um bloco `---` que não parseia é indistinguível de um que parseia para quem só olha a
      # primeira linha — e `ingest.py:162-165` sai com erro num deles. `docs/` nunca é ingerido,
      # então este era o único lugar do repositório onde a falha não tinha sintoma.
      - name: Frontmatter de docs/ parseia
        run: uv run python -m tests.knowledge.frontmatter_parseavel_test
```

- [ ] **Step 7: Confirm the gate is picked up locally**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
uv run --project apps/backend --no-sync python scripts/gates.py --list | grep -i "Frontmatter de docs"
```
Expected: the new gate appears in the derived list.

- [ ] **Step 8: Commit**

```bash
git add apps/backend/tests/knowledge/frontmatter_parseavel_test.py \
        docs/superpowers/specs/2026-08-17-user-managed-agents-and-knowledge-design.md \
        .github/workflows/ci.yml
git commit -m "fix(docs): quote description containing a colon, and gate the class of bug"
```

---

### Task 0.2: Correct the two documentation misstatements

**Files:**
- Modify: `docs/superpowers/specs/2026-08-27-docbundle-vs-okf-medicao.md:12`
- Modify: `CLAUDE.md` (the ADR range string)

**Interfaces:** none. Documentation only.

- [ ] **Step 1: Verify both anchors**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -n '10,14p' docs/superpowers/specs/2026-08-27-docbundle-vs-okf-medicao.md
grep -n "ADRs 001" CLAUDE.md
ls docs/adr/ | grep -c '^ADR-'
```
Expected: a line attributing `SPEC.md` to `GoogleCloudPlatform/knowledge-catalog`; an ADR
range string in `CLAUDE.md`; an ADR count of 33.

- [ ] **Step 2: Fix the repo attribution**

Change the citation from `GoogleCloudPlatform/knowledge-catalog` to
`GoogleCloudPlatform/open-knowledge-format`, and append the pinned commit
`ad30107c31c06aec8a7d5636e0d1058118604e6f`. **Keep the line count (1006)** — it is correct,
and it is the evidence that the right file was read from the wrong-named repo.

- [ ] **Step 3: Fix the ADR range**

Update `CLAUDE.md`'s "ADRs 001–023" to the real range, read from the `ls` above — not from
this plan. If Task 2.3 later adds ADR-035, that task updates the range again.

- [ ] **Step 4: Confirm no other stale reference survives**

Run:
```bash
grep -rn "knowledge-catalog" . --include='*.md' --include='*.py' --include='*.ts' \
  | grep -v node_modules | grep -v '/.git/'
```
Expected: no output. If any hit remains, fix it in this task.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-27-docbundle-vs-okf-medicao.md CLAUDE.md
git commit -m "docs: correct OKF spec repo attribution and ADR range"
```

---

### Task 0.3: Remove the writer instruction the pipeline overrides

**Files:**
- Modify: `apps/backend/app/modules/knowledge/skills/wiki-page-writer/SKILL.md:47-54`
- Read only: `apps/backend/app/modules/knowledge/internal/wiki_builder.py:198-200,354`

**Interfaces:**
- Produces: a skill file with no frontmatter template. Task 2.1 depends on this, because
  it makes the builder the sole author of frontmatter.

**Rationale:** the skill mandates VitePress frontmatter (`title`, `description`, no `type`)
and `wiki_builder.py:354` tells the model to emit none — in the same pipeline that loads
the skill into the writer prompt (`_writer_rules`, `:198-200`). One instruction is dead and
neither file shows which. The skill's own template would also fail §11.2 for lacking `type`.

- [ ] **Step 1: Read both sides**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -n '45,56p' apps/backend/app/modules/knowledge/skills/wiki-page-writer/SKILL.md
sed -n '196,203p;352,356p' apps/backend/app/modules/knowledge/internal/wiki_builder.py
```
Expected: a `### VitePress Frontmatter` block with a fenced `title`/`description` template;
`def _writer_rules()` reading the skill file; the string `sem frontmatter VitePress`.

- [ ] **Step 2: Replace the dead template**

In `SKILL.md`, replace the whole `### VitePress Frontmatter` section (heading, prose and
fenced block) with:

```markdown
### Frontmatter

Do not emit frontmatter. The pipeline writes it after you return, so that `type` and the
producer actor stay out of reach of a prompt — see `wiki_builder.render_page`.
```

Leave the `### Citations` rules (`:67-75`) **untouched**. They are live, and Task 2.1
depends on the citation format not moving.

- [ ] **Step 3: Confirm the pipeline still loads the skill**

Run:
```bash
cd apps/backend && uv run python -c "
from app.modules.knowledge.internal.wiki_builder import _writer_rules
r = _writer_rules()
assert r.strip(), 'skill file read as empty'
assert 'VitePress' not in r, 'the dead template is still in the prompt'
assert 'Citations' in r, 'the live citation rules were removed by mistake'
print('ok —', len(r), 'chars of writer rules, citations intact')
"
```
Expected: `ok — <n> chars of writer rules, citations intact`.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/app/modules/knowledge/skills/wiki-page-writer/SKILL.md
git commit -m "docs(skills): drop the frontmatter template the pipeline overrides"
```

---

# PHASE 1 — Primitives, and a gate that names its blind spots

Still no artifact changes. CI green throughout.

---

### Task 1.1: OKF actor and timestamp helpers

**Files:**
- Create: `apps/backend/app/modules/okf/internal/actors.py`
- Modify: `apps/backend/app/modules/okf/public.py`
- Create: `apps/backend/tests/okf/actors_test.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces, exported from `app.modules.okf.public`:
  - `agent_actor(producer: str, version: str) -> str`
  - `process_actor(name: str, version: str | None = None) -> str`
  - `human_actor(identifier: str) -> str`
  - `okf_timestamp(moment: datetime | None = None) -> str`
  - `generated_block(by: str, at: str | None = None) -> dict[str, str]`
  - `verified_entry(by: str, at: str | None = None) -> dict[str, str]`

  Tasks 2.1 and 2.2 import these **from `app.modules.okf.public`**, never from `internal`.

- [ ] **Step 1: Write the failing gate**

Create `apps/backend/tests/okf/actors_test.py`:

```python
"""Strings de ator e timestamps no vocabulário do OKF v0.2 (§5 e §7).

SPEC.md:489-501 — `<produtor>/<versão>` para agente ou ferramenta, `human:<id>` para
pessoa, `process:<id>` para processo automatizado. O trust tier (SPEC.md:403-407) é
derivado do prefixo `human:`, então um ator de máquina que o carregue forja uma revisão
humana — é a única falha aqui que é silenciosa e cara.

SPEC.md:284-285 — todo timestamp é ISO 8601 com offset UTC explícito. Data pura não serve.

    uv run python -m tests.okf.actors_test
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from app.modules.okf.public import (
    agent_actor,
    generated_block,
    human_actor,
    okf_timestamp,
    process_actor,
    verified_entry,
)


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    def levanta(nome: str, fn) -> None:
        try:
            fn()
        except ValueError:
            check(nome, True)
        else:
            check(nome, False)

    check("agente é <produtor>/<versão>", agent_actor("openwiki", "0.4.3") == "openwiki/0.4.3")
    check("processo sem versão", process_actor("wiki-verifier") == "process:wiki-verifier")
    check(
        "processo com versão",
        process_actor("wiki-verifier", "1") == "process:wiki-verifier/1",
    )
    check("pessoa é human:<id>", human_actor("jefferson") == "human:jefferson")

    check(
        "ator de agente nunca reivindica human:",
        not agent_actor("openwiki", "0.4.3").startswith("human:"),
    )
    check(
        "ator de processo nunca reivindica human:",
        not process_actor("wiki-verifier", "1").startswith("human:"),
    )

    levanta("produtor vazio é recusado", lambda: agent_actor("", "0.4.3"))
    levanta("versão vazia é recusada", lambda: agent_actor("openwiki", ""))
    levanta("produtor com `/` é recusado", lambda: agent_actor("open/wiki", "0.4.3"))
    levanta("produtor com `:` é recusado", lambda: agent_actor("open:wiki", "0.4.3"))
    levanta("nome de processo vazio é recusado", lambda: process_actor("  "))

    utc = okf_timestamp(datetime(2026, 9, 2, 14, 30, 0, tzinfo=timezone.utc))
    check("timestamp é ISO com offset", utc == "2026-09-02T14:30:00+00:00")
    levanta(
        "datetime ingênuo é recusado",
        lambda: okf_timestamp(datetime(2026, 9, 2, 14, 30, 0)),
    )
    recife = timezone(timedelta(hours=-3))
    check(
        "outro offset é normalizado para UTC",
        okf_timestamp(datetime(2026, 9, 2, 11, 30, 0, tzinfo=recife)) == "2026-09-02T14:30:00+00:00",
    )
    agora = okf_timestamp()
    check("sem argumento usa o agora, com offset", agora.endswith("+00:00"))

    check(
        "generated tem a forma {by, at}",
        generated_block("openwiki/0.4.3", "2026-09-02T14:30:00+00:00")
        == {"by": "openwiki/0.4.3", "at": "2026-09-02T14:30:00+00:00"},
    )
    levanta("generated.by é obrigatório (SPEC.md:377)", lambda: generated_block(""))
    check(
        "verified tem a forma {by, at}",
        verified_entry("process:wiki-verifier/1", "2026-09-02T14:31:00+00:00")
        == {"by": "process:wiki-verifier/1", "at": "2026-09-02T14:31:00+00:00"},
    )
    levanta("verified[].by é obrigatório", lambda: verified_entry(" "))

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} failure(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd apps/backend && uv run python -m tests.okf.actors_test`
Expected: `ImportError` — the names are not exported from `app.modules.okf.public`.

- [ ] **Step 3: Write the implementation**

Create `apps/backend/app/modules/okf/internal/actors.py`:

```python
"""Atores e timestamps do OKF v0.2.

SPEC.md:489-501 (convenção de ator), SPEC.md:284-285 (timestamps),
SPEC.md:366-380 (`generated`), SPEC.md:384-399 (`verified`).

NADA AQUI PODE ENTRAR NUMA DECISÃO DE AUTORIZAÇÃO. O trust tier derivado destes campos é
sinal consultivo e explicitamente NÃO é controle de acesso (SPEC.md:410). O acesso deste
repositório segue a fonte (ADR-031) e não passa por aqui.

POR QUE `_require` RECUSA `/` E `:`. Os dois são separadores da própria convenção: um
produtor chamado `open/wiki` produziria `open/wiki/0.4.3`, que relê como produtor `open` na
versão `wiki/0.4.3`. E um prefixo com `:` deixaria `human` alcançável por acidente — que é
a única falha desta camada que muda o trust tier sem nenhum outro sintoma.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = [
    "agent_actor",
    "generated_block",
    "human_actor",
    "okf_timestamp",
    "process_actor",
    "verified_entry",
]


def _require(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} deve ser texto não vazio")
    if "/" in cleaned or ":" in cleaned:
        raise ValueError(f"{field} não pode conter '/' nem ':': {value!r}")
    return cleaned


def agent_actor(producer: str, version: str) -> str:
    """Um agente ou ferramenta: `<produtor>/<versão>` (SPEC.md:494)."""
    return f"{_require(producer, 'producer')}/{_require(version, 'version')}"


def process_actor(name: str, version: str | None = None) -> str:
    """Um processo automatizado: `process:<id>`, versionado quando houver versão."""
    base = f"process:{_require(name, 'name')}"
    return f"{base}/{_require(version, 'version')}" if version is not None else base


def human_actor(identifier: str) -> str:
    """Uma pessoa: `human:<id>`. Só para ação humana de verdade (SPEC.md:500-501)."""
    return f"human:{_require(identifier, 'identifier')}"


def okf_timestamp(moment: datetime | None = None) -> str:
    """ISO 8601 em UTC com offset explícito, precisão de segundo."""
    if moment is None:
        moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("datetime ingênuo recusado; o OKF exige offset UTC explícito")
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def generated_block(by: str, at: str | None = None) -> dict[str, str]:
    """SPEC.md:377 — `by` é obrigatório dentro de `generated`."""
    if not (by or "").strip():
        raise ValueError("generated.by é obrigatório")
    return {"by": by.strip(), "at": at or okf_timestamp()}


def verified_entry(by: str, at: str | None = None) -> dict[str, str]:
    """Um evento de verificação (SPEC.md:384-399)."""
    if not (by or "").strip():
        raise ValueError("verified[].by é obrigatório")
    return {"by": by.strip(), "at": at or okf_timestamp()}
```

- [ ] **Step 4: Export from the module's public surface**

In `apps/backend/app/modules/okf/public.py`:
- Add, alongside the existing imports:
  ```python
  from app.modules.okf.internal.actors import (
      agent_actor,
      generated_block,
      human_actor,
      okf_timestamp,
      process_actor,
      verified_entry,
  )
  ```
- Add the six names to `__all__`, keeping its existing alphabetical ordering.

- [ ] **Step 5: Run it and confirm it passes**

Run: `cd apps/backend && uv run python -m tests.okf.actors_test`
Expected: exit 0, `✅ 0 failure(s)`.

- [ ] **Step 6: Confirm the architecture gates still hold**

Run:
```bash
cd apps/backend
uv run lint-imports --config importlinter.toml
uv run python -m tests.architecture.filesystem_anchors_test
uv run python -m tests.architecture.module_graph_test
```
Expected: all three pass. `module_graph` is unchanged because `actors.py` adds no
inter-module edge — it imports only the stdlib.

- [ ] **Step 7: Register the gate in CI**

In `.github/workflows/ci.yml`, after the `tests.okf.changeset_test` line (and after the
gate added in Task 0.1), add:

```yaml
      # A convenção de ator do OKF (SPEC.md:489-501) tem uma falha silenciosa: um ator de
      # máquina que comece com `human:` sobe o trust tier para "human-reviewed" sem nenhum
      # outro sintoma. Este gate é o que impede um produtor novo de reintroduzi-la.
      - name: OKF — atores e timestamps
        run: uv run python -m tests.okf.actors_test
```

- [ ] **Step 8: Commit**

```bash
git add apps/backend/app/modules/okf/internal/actors.py \
        apps/backend/app/modules/okf/public.py \
        apps/backend/tests/okf/actors_test.py \
        .github/workflows/ci.yml
git commit -m "feat(okf): add actor and timestamp helpers per SPEC v0.2 §5/§7"
```

---

### Task 1.2: Make the gate name the wiki directories it does not check

**Files:**
- Modify: `apps/backend/tests/knowledge/okf_conformance_test.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a module-level `EXCLUDED_BUNDLES: dict[str, str]` mapping each unchecked
  wiki-shaped directory to the reason. Task 4.3 removes one entry from it.

**Rationale:** the gate prints `✅ os 4 bundles são OKF v0.2 conformantes (§11)` while the
artifact the `selfwiki` domain actually queries is not among the four, and its absence is
invisible in the output. Severity of the `okf_version` warning is **not** changed here —
that is Task 3.2, after the regeneration that makes it satisfiable.

- [ ] **Step 1: Verify the anchors**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -n '32,52p' apps/backend/tests/knowledge/okf_conformance_test.py
sed -n '86,102p' apps/backend/tests/knowledge/okf_conformance_test.py
```
Expected: `BACKEND`/`REPO` anchored on `app`; `BUNDLES` as a module-level dict of four
entries with justifying comments; a pass/fail branch reading only `errors`; a final
`print` naming a count.

If `EXCLUDED_BUNDLES` already exists, mark this task complete and record it as stale.

- [ ] **Step 2: Add the exclusion map**

In `okf_conformance_test.py`, immediately after the `BUNDLES` dict, add:

```python
#: Diretórios com cara de bundle que este gate NÃO mede, e por quê. Existe porque a saída
#: dizia "os 4 bundles são conformantes" sem dizer que o bundle que o `selfwiki` consulta não
#: era um dos quatro — um verde que afirma mais do que mediu, que é exatamente a falha que o
#: `docs/CASE-STUDY-LLM-WIKI-LOOP.md` documenta.
#:
#: Entrar aqui é uma decisão, não um esquecimento: a lista é impressa em toda execução.
EXCLUDED_BUNDLES = {
    "knowledge/wiki-bundle": (
        "o frontmatter é retirado na adaptação (adapt_openwiki.py:191-194) — É O ARTEFATO "
        "QUE O DOMÍNIO selfwiki CONSULTA; entra no gate na Fase 4 do plano de adoção OKF"
    ),
    "agents/assured/guardrails": (
        "dado de aplicação, deliberadamente não é conceito AgentSchema "
        "(guardrails/response-language.md:2)"
    ),
    "agents/assured/personas": "idem — persona compartilhada, não conceito",
}
```

- [ ] **Step 3: Print the exclusions on every run**

In `main()`, before the final success/failure print, add:

```python
    print("\n  não medidos (decisão, não esquecimento):")
    for nome, motivo in EXCLUDED_BUNDLES.items():
        print(f"    – {nome}: {motivo}")
```

And change the success line so it names what it checked and claims nothing else:

```python
    print(f"\n✅ os {len(BUNDLES)} bundles medidos são OKF v0.2 conformantes (§11): "
          f"{', '.join(BUNDLES)}")
```

- [ ] **Step 4: Run the gate**

Run: `cd apps/backend && uv run python -m tests.knowledge.okf_conformance_test`
Expected: **exit 0** (unchanged), the four bundles still `✓`, plus the three exclusions
printed with their reasons, and a success line that names the four.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/tests/knowledge/okf_conformance_test.py
git commit -m "fix(okf): gate names the wiki dirs it does not measure, with reasons"
```

---

# ✅ GATE A — ANSWERED: **A1**

Decided 2026-09-02. Recorded here because Phase 2 is only legible with the reasoning
attached; the question itself is closed and no halt remains.

### The question that was asked

When **our own** `wiki_builder` verifier pass rewrites a page, should that be recorded in
the page's frontmatter as `verified: [{ by: process:<name>/<version>, at: <iso> }]`?

### The answer

**A1 — machine verification in the bundle, human sign-off in the audit trail.** Do Tasks
2.1, 2.2 and 2.3.

### What was reported before the decision, and a correction it produced

**The argument against A1 is not where the audit said it was.** The audit and the first
draft of this plan attributed it to ADR-023. Verified: `docs/adr/ADR-023-evidence-layer.md`
is about the **HITL approval evidence layer** ("Azure owns immutability, we own the event"),
its status is **`Proposed`**, and it does not mention `verified` in a document at all. The
rationale exists only in a test docstring,
`apps/backend/tests/foundry/provenance_okf_test.py:21-23`:

> *"a identidade **não** vem do documento: mesmo que a tela mande um `verified`, quem decide
> é `actor()`. Um documento que pudesse declarar quem o verificou seria um documento capaz
> de forjar a própria revisão"*

And its subject is **the screen sending `verified`** on a published Foundry resource —
untrusted client input the backend overrides with `actor()`. Our wiki verifier runs
server-side with no client in the loop, so that threat does not reach this case. That is
what makes A1 defensible rather than merely convenient, and it is why **Task 2.3 writes a
new, standalone ADR rather than an amendment**: there is nothing in ADR-023 to amend, and
ADR-023 is not accepted anyway.

**The verifier's identity did not exist** and was chosen here: `wiki_builder.py` carries no
version of its own, and what changes the quality of a verification pass is the model
deployment (`resolved_model`, `:303`). See the actor decision recorded below.

**A `--no-verify` run is not distinguishable today.** `manifest.json` carries `key`,
`title`, `source`, `language`, `model`, `generatedAt`, `kind`, `component`,
`componentVersion`, `releaseVersion`, `pages`, `groups` — no verification field. The only
trace is the log line at `wiki_builder.py:389`, which does not survive into the artifact.
Task 2.2 is what changes that, and `SPEC.md:405` is why absence must stay absence.

### For the record: what A2 and A3 would have meant

- **A2 — nothing of ours in the bundle:** Task 2.1 only. Pages from `wiki_builder` would
  stay permanently `unverified` to an OKF consumer.
- **A3 — human sign-off in the bundle too:** rejected. There the forgery threat *is* real,
  because the origin is the screen.

---

# PHASE 2 — Our producer emits the trust family

**Precondition:** Gate A answered **A1**. **Target artifact:** `knowledge/wiki-bundle/**`,
written by `wiki_builder.py` — *not* `openwiki/`, which Phase 4 regenerates.

---

### Task 2.1: The builder writes `type` and `generated` onto every page

**Files:**
- Modify: `apps/backend/app/modules/knowledge/internal/wiki_builder.py` (page write at
  `:399`; model resolution at `:303`)
- Create: `apps/backend/tests/knowledge/wiki_frontmatter_test.py`
- Modify: `apps/backend/tests/architecture/module_graph.json`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `agent_actor`, `generated_block` from `app.modules.okf.public` (Task 1.1).
- Produces:
  `render_page(*, body: str, title: str, producer: str, version: str, description: str | None = None, type_: str = "reference") -> str`
  Task 2.2 consumes `render_page`'s output shape; Task 4.1 relies on the block surviving
  the adapter.

**Design constraint:** the model must **not** author the frontmatter. The builder writes it
after the model returns prose, so `type` and the actor stay out of reach of a prompt. This
is why Task 0.3 removed the skill's template instead of fixing it.

**One visible choice:** `type_` defaults to `"reference"`. `SPEC.md:182-186` leaves type
values unregistered; `"reference"` matches both the spec's own example list and
`DOCS-STANDARD.md`'s vocabulary. Say so when reporting the task — it is a producer
decision, not a spec requirement.

- [ ] **Step 1: Verify the anchors**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -n '300,306p;394,404p' apps/backend/app/modules/knowledge/internal/wiki_builder.py
grep -n "write_text" apps/backend/app/modules/knowledge/internal/wiki_builder.py
```
Expected: `resolved_model = model or tenant_config().foundry_model` at `:303`; a loop over
`pages` writing `page["content"]` to `bundle / "pages" / f"{norm}.md"` at `:399`; exactly
three `write_text` calls (page, manifest, llms.txt).

- [ ] **Step 2: Write the failing gate**

Create `apps/backend/tests/knowledge/wiki_frontmatter_test.py`:

```python
"""As páginas que o `wiki_builder` escreve carregam procedência OKF v0.2.

Fecha o gap G2 da auditoria de 2026-09-02: nenhum conceito de nenhum bundle carregava
`generated`, então toda página lia como não-atribuída E não-verificada para um consumidor
OKF — inclusive as que o verificador tinha reescrito.

A REGRA QUE ESTE GATE EXISTE PARA SEGURAR: o modelo não escreve o frontmatter. Se ele
emitir um bloco próprio, `render_page` o descarta e escreve o dele por cima. Um documento
capaz de declarar o próprio `type` e o próprio ator é um documento capaz de forjar a
própria procedência — e o prompt é a superfície mais barata de influenciar que existe.

    uv run python -m tests.knowledge.wiki_frontmatter_test
"""

from __future__ import annotations

import sys

import yaml

from app.modules.knowledge.internal.wiki_builder import render_page

CORPO = "## Visão geral\n\nProsa citando `apps/backend/app/main.py`.\n"


def frontmatter(texto: str) -> dict:
    assert texto.startswith("---"), "página sem bloco de frontmatter"
    _, _, resto = texto.partition("---")
    bloco, sep, _ = resto.partition("\n---")
    assert sep, "bloco de frontmatter não fechado"
    return yaml.safe_load(bloco) or {}


def pagina(corpo: str = CORPO) -> str:
    return render_page(
        body=corpo,
        title="Ponto de entrada do backend",
        producer="foundry-wiki-builder",
        version="gpt-5-mini",
    )


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    meta = frontmatter(pagina())
    check("type presente e não vazio (SPEC.md:187)", bool(str(meta.get("type", "")).strip()))
    check("title veio do chamador", meta.get("title") == "Ponto de entrada do backend")
    check(
        "generated.by é <produtor>/<versão>",
        meta.get("generated", {}).get("by") == "foundry-wiki-builder/gpt-5-mini",
    )
    check(
        "generated.at tem offset explícito (SPEC.md:284)",
        str(meta.get("generated", {}).get("at", "")).endswith("+00:00"),
    )
    check(
        "generated.by nunca reivindica human:",
        not str(meta["generated"]["by"]).startswith("human:"),
    )
    check("sem verified: ausência é 'unverified' (SPEC.md:405)", "verified" not in meta)
    check(
        "description ausente não vira chave vazia",
        "description" not in meta,
    )

    check("o corpo sai intacto abaixo do bloco", pagina().endswith(CORPO))

    forjada = pagina("---\ntype: Forjado\ngenerated: {by: 'human:alguem'}\n---\n\n## Real\n")
    meta_f = frontmatter(forjada)
    check("bloco emitido pelo modelo não vira o frontmatter", meta_f.get("type") != "Forjado")
    check(
        "…e o ator continua sendo o do produtor",
        meta_f["generated"]["by"] == "foundry-wiki-builder/gpt-5-mini",
    )
    check("…e o corpo real sobrevive", forjada.rstrip().endswith("## Real"))

    com_desc = render_page(
        body=CORPO, title="T", description="Uma frase.",
        producer="p", version="v",
    )
    check("description passa quando dada", frontmatter(com_desc)["description"] == "Uma frase.")

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} failure(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd apps/backend && uv run python -m tests.knowledge.wiki_frontmatter_test`
Expected: `ImportError: cannot import name 'render_page'`.

- [ ] **Step 4: Implement `render_page`**

In `wiki_builder.py`:

- Add to the imports, **from the public surface, never from `internal`**:
  ```python
  from app.modules.okf.public import agent_actor, generated_block
  ```
- Add near the other module constants:
  ```python
  #: O produtor, no vocabulário de ator do OKF (SPEC.md:494). A versão é o deployment de
  #: modelo resolvido em runtime, porque é ele que muda o texto — não a versão deste arquivo.
  _PRODUCER = "foundry-wiki-builder"
  #: `type` é a única chave sempre obrigatória (SPEC.md:187). O valor não é registrado
  #: centralmente (SPEC.md:182-186); `reference` casa com a lista de exemplo da spec e com o
  #: vocabulário do DOCS-STANDARD.md.
  _PAGE_TYPE = "reference"
  ```
- Add the function:
  ```python
  def render_page(
      *,
      body: str,
      title: str,
      producer: str,
      version: str,
      description: str | None = None,
      type_: str = _PAGE_TYPE,
  ) -> str:
      """A página com frontmatter OKF v0.2, escrito AQUI e não pelo modelo.

      Um bloco que o modelo tenha emitido é descartado antes: `frontmatter.split` devolve
      (bloco, corpo) e só o corpo é usado. Ver o docstring do gate para o porquê."""
      _, corpo = frontmatter.split(body)
      meta: dict[str, object] = {"type": type_, "title": title}
      if description:
          meta["description"] = description
      meta["generated"] = generated_block(agent_actor(producer, version))
      bloco = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
      corpo = corpo.lstrip("\n")
      return f"---\n{bloco}\n---\n\n{corpo}"
  ```
- Ensure `yaml` and `from app.modules.knowledge.internal import frontmatter` are imported
  at module level; add whichever is missing.

- [ ] **Step 5: Route the page write through it**

At `wiki_builder.py:399`, replace

```python
        (bundle / "pages" / f"{norm}.md").write_text(page["content"], encoding="utf-8")
```

with

```python
        (bundle / "pages" / f"{norm}.md").write_text(
            render_page(
                body=page["content"],
                title=page["title"],
                producer=_PRODUCER,
                version=resolved_model,
            ),
            encoding="utf-8",
        )
```

`resolved_model` is already in scope from `:303`.

- [ ] **Step 6: Run it and confirm it passes**

Run: `cd apps/backend && uv run python -m tests.knowledge.wiki_frontmatter_test`
Expected: exit 0, `✅ 0 failure(s)`.

- [ ] **Step 7: Re-record the new inter-module edge**

Run:
```bash
cd apps/backend
uv run lint-imports --config importlinter.toml
uv run python -m tests.architecture.module_graph_test
```
Expected: `lint-imports` **passes** (the import is `okf.public`, which the layers contract
allows); `module_graph_test` **fails** with a new `knowledge → okf` edge introduced by
`modules/knowledge/internal/wiki_builder.py`. That failure is correct.

Then:
```bash
uv run python -m tests.architecture.module_graph_test --update
git diff apps/backend/tests/architecture/module_graph.json
```
Expected diff: exactly one added edge, `knowledge → okf`, attributed to
`modules/knowledge/internal/wiki_builder.py`. **If any other edge changed, stop and
report** — something else moved.

- [ ] **Step 8: Confirm the fidelity gate is unmoved**

Run:
```bash
cd apps/backend && uv run python -m eval.wiki_shelf_test
```
Expected: PASS, with the **same** score as before this task. The fidelity regex
(`wiki_builder.py:98`) reads citations out of prose; a YAML block above the prose must not
change the count. **If a fidelity number moves, stop** — the block is being counted as
content, and Task 4.2's strip has to move earlier.

- [ ] **Step 9: Register the gate in CI**

In `.github/workflows/ci.yml`, after the `OKF — atores e timestamps` entry from Task 1.1:

```yaml
      # G2 da auditoria de 2026-09-02: nenhuma página carregava `generated`, então tudo lia
      # como não-atribuído. O gate também segura a regra que importa mais que o campo: o
      # frontmatter é escrito pelo builder, não pelo modelo — um bloco vindo do prompt é
      # descartado.
      - name: Wiki — procedência OKF nas páginas geradas
        run: uv run python -m tests.knowledge.wiki_frontmatter_test
```

- [ ] **Step 10: Commit**

```bash
git add apps/backend/app/modules/knowledge/internal/wiki_builder.py \
        apps/backend/tests/knowledge/wiki_frontmatter_test.py \
        apps/backend/tests/architecture/module_graph.json \
        .github/workflows/ci.yml
git commit -m "feat(okf): builder writes type and generated into page frontmatter"
```

---

### Task 2.2: The verifier pass leaves a `verified` event

**Precondition:** Task 2.1 complete. (Gate A answered **A1**, so this task runs.)

**Files:**
- Modify: `apps/backend/app/modules/knowledge/internal/wiki_builder.py` (verifier accept
  site at `:358-390`; `--no-verify` at `:475`)
- Modify: `apps/backend/tests/knowledge/wiki_frontmatter_test.py` (extend)

**Interfaces:**
- Consumes: `render_page` (2.1), `process_actor` and `verified_entry` from
  `app.modules.okf.public` (1.1).
- Produces:
  `stamp_verified(page: str, *, verifier: str, version: str | None = None) -> str`

**Design constraint:** absence must remain absence. `SPEC.md:405` derives `unverified` from
a **missing key**, so a `--no-verify` run emits no `verified` key — not an empty list, not
a null.

- [ ] **Step 1: Read the verifier and confirm it rewrites in place**

Run: `sed -n '356,392p;473,477p' apps/backend/app/modules/knowledge/internal/wiki_builder.py`
Expected: a `verifier = _agent(...)` definition; inside the page loop, `if verify:` running
the verifier and reassigning `md = v_resp.text`; `pages.append({"title": ..., "content": md})`;
a log line containing `" (verificada)"`; a `--no-verify` CLI flag.

- [ ] **Step 2: Extend the gate**

In `apps/backend/tests/knowledge/wiki_frontmatter_test.py`, add the import

```python
from app.modules.knowledge.internal.wiki_builder import render_page, stamp_verified
```

and insert these checks into `main()`, before the final print:

```python
    carimbada = stamp_verified(pagina(), verifier="wiki-verifier", version="1")
    meta_v = frontmatter(carimbada)
    check(
        "verified é lista com um evento de processo",
        [e["by"] for e in meta_v.get("verified", [])] == ["process:wiki-verifier/1"],
    )
    check(
        "verified[].at tem offset explícito",
        str(meta_v["verified"][0]["at"]).endswith("+00:00"),
    )
    check(
        "o verificador nunca é human: (ADR-023)",
        not meta_v["verified"][0]["by"].startswith("human:"),
    )
    check(
        "generated sobrevive ao carimbo",
        meta_v["generated"] == frontmatter(pagina())["generated"],
    )
    check("o corpo sobrevive ao carimbo", carimbada.endswith(CORPO))

    duas = stamp_verified(carimbada, verifier="fidelity-gate", version="1")
    check(
        "carimbar de novo ACRESCENTA, não substitui",
        [e["by"] for e in frontmatter(duas)["verified"]]
        == ["process:wiki-verifier/1", "process:fidelity-gate/1"],
    )
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd apps/backend && uv run python -m tests.knowledge.wiki_frontmatter_test`
Expected: `ImportError: cannot import name 'stamp_verified'`.

- [ ] **Step 4: Implement `stamp_verified`**

In `wiki_builder.py`:

- Extend the OKF import to:
  ```python
  from app.modules.okf.public import (
      agent_actor,
      generated_block,
      process_actor,
      verified_entry,
  )
  ```
- Add:
  ```python
  def stamp_verified(page: str, *, verifier: str, version: str | None = None) -> str:
      """Acrescenta um evento de verificação ao frontmatter, sem tocar no corpo.

      ACRESCENTA, e nunca substitui: `verified` é uma LISTA de verificações independentes
      (SPEC.md:388-391), e uma passagem nova não desfaz a anterior. Um mapa solto legado é
      normalizado para lista de um elemento, como o §5.2 manda o consumidor tratá-lo."""
      meta, corpo = frontmatter.parse(page)
      atual = meta.get("verified")
      eventos = [atual] if isinstance(atual, dict) else list(atual or [])
      eventos.append(verified_entry(process_actor(verifier, version)))
      meta["verified"] = eventos
      bloco = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
      corpo = corpo.lstrip("\n")
      return f"---\n{bloco}\n---\n\n{corpo}"
  ```

- [ ] **Step 5: Call it where the verified page is accepted**

Inside the page loop in `build_component_wiki`, the `if verify:` branch currently ends with
`md = v_resp.text`. The page is rendered at write time (Task 2.1), so the stamp must be
applied to the **rendered** page, not to raw model text. Change the write site added in
Task 2.1 Step 5 to:

```python
        rendered = render_page(
            body=page["content"],
            title=page["title"],
            producer=_PRODUCER,
            version=resolved_model,
        )
        if page.get("verified"):
            rendered = stamp_verified(rendered, verifier=_VERIFIER, version=resolved_model)
        (bundle / "pages" / f"{norm}.md").write_text(rendered, encoding="utf-8")
```

and, in the page loop, record the fact on the page dict:

```python
            pages.append({"title": p["title"], "content": md, "verified": verify})
```

Add the constant beside `_PRODUCER`:

```python
  #: O passe de verificação, como ator de processo (SPEC.md:497). Nome estável; a versão é o
  #: deployment que rodou, pelo mesmo motivo de `_PRODUCER`.
  _VERIFIER = "wiki-verifier"
```

`--no-verify` sets `verify=False`, so `page["verified"]` is `False` and no key is written.

- [ ] **Step 6: Run it and confirm it passes**

Run: `cd apps/backend && uv run python -m tests.knowledge.wiki_frontmatter_test`
Expected: exit 0. In particular the Task 2.1 check
`sem verified: ausência é 'unverified' (SPEC.md:405)` must still pass — `render_page` alone
never writes the key.

- [ ] **Step 7: Confirm no other gate moved**

Run:
```bash
cd apps/backend
uv run lint-imports --config importlinter.toml
uv run python -m tests.architecture.module_graph_test
uv run python -m eval.wiki_shelf_test
```
Expected: all pass, fidelity score unchanged.

- [ ] **Step 8: Commit**

```bash
git add apps/backend/app/modules/knowledge/internal/wiki_builder.py \
        apps/backend/tests/knowledge/wiki_frontmatter_test.py
git commit -m "feat(okf): verifier pass stamps a process: verified event on the page"
```

---

### Task 2.3: Record the Gate A decision as ADR-035

**Precondition:** Task 2.2 complete.

**Files:**
- Create: `docs/adr/ADR-035-okf-machine-verification-in-bundle.md`
- Modify: `docs/adr/README.md`
- Modify: `CLAUDE.md` (ADR range, again)

**Note on the number:** ADR-034 is taken by
`.smart-coding/_adrs/ADR-034-authoring-area-and-git-first-publication.md`. Confirm with
`ls docs/adr/ .smart-coding/_adrs/` before writing, and take the next free number if 035 is
also claimed by then.

**Note on ADR-023 — read before writing.** The first draft of this plan had ADR-035
*amending* ADR-023. It does not, and `ADR-023-evidence-layer.md` must **not** be edited by
this task. ADR-023 is about the HITL approval evidence layer, it is still `Proposed`, and
it says nothing about `verified` in a document. The rationale this decision engages with
lives in `apps/backend/tests/foundry/provenance_okf_test.py:21-23`, and it is about
untrusted client input, not about documents in general. ADR-035 is a new, standalone
decision that narrows nothing already decided.

- [ ] **Step 1: Verify that ADR-023 really is silent on this**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
grep -n -i "verified\|forjar\|frontmatter" docs/adr/ADR-023-evidence-layer.md
grep -n "Status:" docs/adr/ADR-023-evidence-layer.md
sed -n '18,26p' apps/backend/tests/foundry/provenance_okf_test.py
```
Expected: no hit in ADR-023 asserting that `verified` must stay out of a document;
`- **Status:** Proposed`; the forgery paragraph present in the test docstring, phrased
about "a tela" (the screen).

**If ADR-023 does contain the rule**, stop and report — the ADR is the authority, this
plan is not, and Gate A would need to be reopened.

- [ ] **Step 2: Write ADR-035**

Follow the structure of the neighbouring ADRs in `docs/adr/`. It must state:

- **Context:** OKF v0.2 §5.2 makes `generated` and `verified` first-class; our verifier
  pass left no trace in the artifact (audit gap G3); the external generator already writes
  machine `verified` into `openwiki/` on its own (`src/okf/claims-verification.ts:26-28`,
  clone `64903f9`), so the repository was going to carry machine verification either way.
- **Decision:** machine verification by this repository's own pipeline is recorded in
  concept frontmatter as `process:<name>/<version>` — concretely
  `process:wiki-verifier/<model deployment>`. Human sign-off is out of scope and stays
  where it already is.
- **Rationale:** two threat models, and only one of them is a document problem. A
  *client-supplied* `verified` is self-attestation by a party we do not control — that is
  the case `provenance_okf_test.py:21-23` refuses, and it refuses it by having the backend
  override with `actor()`. A *server-side* record that our own verifier ran is our tool's
  own output, worth exactly what the fidelity gate over it is worth
  (`eval/assurance.yaml:20`, `build.fidelity_min: 0.80`). Nothing here changes the first
  case.
- **Consequences:** OKF consumers derive `machine-confirmed` rather than `unverified`
  (`SPEC.md:405`) for verified pages; a `--no-verify` run stays `unverified` by carrying no
  key at all; no trust field is read for any authorization decision (`SPEC.md:410`), and
  none may become one — the access path stays `groups:` → `permissionFilter` (ADR-031),
  untouched.
- **Status:** accepted.

- [ ] **Step 3: Update the index and the range**

Add ADR-035 to `docs/adr/README.md` in the existing format. Update the ADR range in
`CLAUDE.md` (fixed once in Task 0.2) to include 035. **Do not touch ADR-023.**

- [ ] **Step 4: Verify nothing else moved**

Run: `git diff --stat docs/adr/`
Expected: exactly two paths — the new `ADR-035-*.md` and `README.md`. If
`ADR-023-evidence-layer.md` appears, revert that file.

- [ ] **Step 5: Commit**

```bash
git add docs/adr/ CLAUDE.md
git commit -m "docs(adr): ADR-035 records machine verification in the bundle"
```

---

# PHASE 3 — Frontmatter survives into the bundle, and never reaches retrieval

**Precondition:** Phase 2 complete. Gate B is closed as **B1** (see the top of this
document); no halt here.

**Why this comes before the regeneration:** with the adapter already preserving
frontmatter, the single dispatch in Phase 4 produces a correct `openwiki/` **and** a
correct `knowledge/wiki-bundle/` in one pull request. Doing it the other way round would
need a second run, or a local adapter re-run, to fix the bundle afterwards.

**The pair that must land together:** Task 3.1 keeps the block in the file; Task 3.2 stops
it from reaching the index. Landing 3.1 alone would put YAML into the retrieval corpus —
the exact outcome `adapt_openwiki.py:22-24` and `ingest.py:137-142` exist to prevent.
Commit them separately for reviewability, but do not merge 3.1 without 3.2.

---

### Task 3.1: The adapter stops discarding the frontmatter block

**Files:**
- Modify: `apps/backend/app/modules/knowledge/internal/adapt_openwiki.py:191-194`
- Create: `apps/backend/tests/knowledge/bundle_frontmatter_roundtrip_test.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `adapt_openwiki` writes `front_matter + body` to each `pages/page-N.md`.
  Task 3.2 consumes that shape; Task 4.3 gates it.

- [ ] **Step 1: Verify the anchors**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -n '86,100p;188,196p' apps/backend/app/modules/knowledge/internal/adapt_openwiki.py
```
Expected: `_split_front_matter` returning `(f"---\n{cru}\n---\n" if cru else "", corpo)`;
a loop that computes `front_matter, body`, flattens links, and writes
`body.lstrip("\n")` — discarding `front_matter`.

- [ ] **Step 2: Write the failing gate**

Create `apps/backend/tests/knowledge/bundle_frontmatter_roundtrip_test.py`:

```python
"""O frontmatter atravessa a adaptação e PARA antes do índice.

DUAS METADES DE UMA DECISÃO SÓ, e é por isso que elas moram no mesmo gate:

  adapt_openwiki      PRESERVA  — a procedência OKF é do documento, e some se for jogada fora
  ingest_docbundles   RETIRA    — o corpo da página É o texto indexado; YAML ali vira corpus

A auditoria de 2026-09-02 registrou a primeira metade como gap G1 e a segunda como o motivo
real do descarte — que nunca foi o `docbundle.schema.json` (13 propriedades, todas de
manifest; zero ocorrências de `content`/`body`/`frontmatter`/`hash`). Preservar sem retirar
faria o modelo citar `generated:` como se fosse conteúdo da página.

O TESTE É PONTA A PONTA de propósito. Uma versão anterior deste gate casava o texto-fonte do
adaptador com `inspect.getsource`; isso passa a verificar como o código está escrito em vez
do que ele faz, e quebra no primeiro `black` sem que nada tenha regredido.

    uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from app.modules.knowledge.internal.adapt_openwiki import _split_front_matter, adapt
from app.modules.knowledge.internal.ingest_docbundles import collect_pages

PAGINA = (
    "---\n"
    "type: concept\n"
    "title: Pipeline de conhecimento\n"
    'generated: { by: "openwiki/0.4.3", at: "2026-09-02T14:30:00+00:00" }\n'
    "---\n"
    "\n"
    "## Visão geral\n"
    "\n"
    "Prosa citando `apps/backend/app/main.py`.\n"
)


def _wiki_falsa(raiz: Path) -> Path:
    """Um repositório mínimo com saída de OpenWiki: um índice e uma página de conteúdo."""
    wiki = raiz / "repo" / "openwiki"
    (wiki / "backend").mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# Directories\n\n- [backend](backend/)\n", encoding="utf-8"
    )
    (wiki / "backend" / "index.md").write_text(
        "# Files\n\n- [Pipeline](knowledge-pipeline.md) - o pipeline\n", encoding="utf-8"
    )
    (wiki / "backend" / "knowledge-pipeline.md").write_text(PAGINA, encoding="utf-8")
    return raiz / "repo"


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    # --- o helper, que já estava certo: guarda de regressão para o passo seguinte
    fm, corpo = _split_front_matter(PAGINA)
    check("o split separa bloco e corpo", fm.startswith("---") and corpo.lstrip().startswith("##"))
    check("nada de YAML sobra no corpo devolvido", "generated:" not in corpo)

    # --- metade 1: a adaptação PRESERVA
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        repo = _wiki_falsa(raiz)
        bundle = adapt(
            repo=repo,
            component="comp",
            version="v1",
            out_dir=raiz / "out",
            wiki_dir=None,
            language="pt-br",
        )
        pagina_adaptada = (bundle / "pages" / "page-1.md").read_text(encoding="utf-8")

        check("a página adaptada mantém o bloco", pagina_adaptada.startswith("---\n"))
        check("…com a procedência intacta", '"openwiki/0.4.3"' in pagina_adaptada)
        check("…e com o corpo intacto", "apps/backend/app/main.py" in pagina_adaptada)

        # --- metade 2: o ingest RETIRA
        itens, _ = collect_pages(raiz / "out")
        check("collect_pages devolveu a página", len(itens) == 1)
        if itens:
            texto = itens[0][1].decode("utf-8")
            check("nenhum delimitador de frontmatter no blob", not texto.lstrip().startswith("---"))
            check(
                "nenhuma chave OKF vaza para o índice",
                "generated:" not in texto and "type:" not in texto,
            )
            check("o cabeçalho do ingest continua na frente", texto.startswith("# "))
            check("a prosa sobreviveu", "apps/backend/app/main.py" in texto)

    print(f"\n{'❌' if falhas else '✅'} {len(falhas)} failure(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: `json` is imported because `collect_pages` reads the `manifest.json` that `adapt`
wrote; no fixture manifest is hand-built, so the manifest contract is exercised too.
If `ruff` flags `json` as unused, remove the import — nothing else depends on it.

- [ ] **Step 3: Run it and confirm the preservation half fails**

Run: `cd apps/backend && uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test`
Expected: exit 1. The two `_split_front_matter` checks pass (the helper is already right),
`a página adaptada mantém o bloco` and `…com a procedência intacta` **fail**, and the
`collect_pages` checks pass **for the wrong reason** — there is no block to leak yet.

If `adapt` raises `SystemExit: no content pages`, the fixture is wrong: `_SKIP_NAMES`
(`adapt_openwiki.py:66`) excludes `index.md`, so the content page must not be named that.

- [ ] **Step 4: Preserve the block at the write site**

At `adapt_openwiki.py:194`, replace

```python
        (bundle / "pages" / f"{norm}.md").write_text(body.lstrip("\n"), encoding="utf-8")
```

with

```python
        # O bloco viaja COM a página (gap G1 da auditoria de 2026-09-02). Ele é retirado em
        # `ingest_docbundles.collect_pages`, antes de virar texto indexado — que é onde o
        # descarte sempre pertenceu, e não aqui.
        (bundle / "pages" / f"{norm}.md").write_text(
            front_matter + body.lstrip("\n"), encoding="utf-8"
        )
```

Then update the module docstring at `:22-38`. The paragraph beginning `Front matter is
stripped:` and the paragraph beginning `E O QUE A v0.2 TROUXE JUNTO` are now false. Replace
both with a statement that:
- the block travels with the page and is removed at index time by
  `ingest_docbundles.collect_pages`;
- the `docbundle.schema.json` constraint the old text cited governs `manifest.json` only —
  13 properties, none of them page content — so no sidecar file is needed;
- the `title` is still lifted from the block by `_title_of`, which is unchanged.

**Do not delete the reference to
`docs/superpowers/specs/2026-08-27-openwiki-claims-medicao.md`** — that measurement is what
proves real v0.2 front matter survives `_split_front_matter` without leaking YAML, and it is
now the evidence *for* this change rather than a note about a deferred one.

- [ ] **Step 5: Run it and confirm the failure MOVED**

Run: `cd apps/backend && uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test`
Expected: exit 1 still — but the failing checks have changed. Preservation now passes, and
`nenhum delimitador de frontmatter no blob` plus `nenhuma chave OKF vaza para o índice`
now fail, because the block reaches the index. Closing those is Task 3.2's job.

**This is the one task in the plan that ends with a red gate.** It is exactly why 4.1 and
4.2 must not be merged apart: commit them separately for reviewability, on the same branch,
and open one pull request covering both.

- [ ] **Step 6: Register the gate in CI**

In `.github/workflows/ci.yml`, after the `Wiki — procedência OKF nas páginas geradas` entry
from Task 2.1, add:

```yaml
      # As duas metades da mesma decisão: o bloco atravessa a adaptação e para antes do índice.
      # Preservar sem retirar colocaria YAML no corpus de retrieval, e o modelo passaria a citar
      # `generated:` como conteúdo da página. O gate é ponta a ponta — roda o adaptador e o
      # ingest de verdade sobre uma wiki de mentira, em vez de casar texto-fonte.
      - name: Bundle — frontmatter preservado no arquivo, retirado no índice
        run: uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test
```

- [ ] **Step 7: Commit (red; do not merge without Task 3.2)**

```bash
git add apps/backend/app/modules/knowledge/internal/adapt_openwiki.py \
        apps/backend/tests/knowledge/bundle_frontmatter_roundtrip_test.py \
        .github/workflows/ci.yml
git commit -m "feat(okf): adapter preserves the frontmatter block in the bundle"
```

---

### Task 3.2: The ingest strips the block before it becomes indexed text

**Files:**
- Modify: `apps/backend/app/modules/knowledge/internal/ingest_docbundles.py:249-256`
- Modify: `apps/backend/tests/knowledge/bundle_frontmatter_roundtrip_test.py` (extend)

**Interfaces:**
- Consumes: pages written by Task 3.1.
- Produces: `collect_pages` returns blob content with no YAML block.

- [ ] **Step 1: Verify the anchor**

Run: `sed -n '244,258p' apps/backend/app/modules/knowledge/internal/ingest_docbundles.py`
Expected: `body = page_file.read_text(...)`, a branch dropping a leading `# ` H1, then
`content = f"# {label} — {title}\n\n{body}"` and `items.append((blob, content.encode("utf-8")))`.

- [ ] **Step 2: Confirm which checks are red**

The gate already contains this half — Task 3.1 Step 2 wrote it, and Task 3.1 Step 5 left it
failing. Nothing to write here.

Run: `cd apps/backend && uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test`
Expected: exit 1, with exactly these two lines `✗`:

```
  ✗ nenhum delimitador de frontmatter no blob
  ✗ nenhuma chave OKF vaza para o índice
```

If any preservation check is also `✗`, Task 3.1 is incomplete — go back.
If `collect_pages` raises instead, its signature drifted from
`(docbundles: Path) -> tuple[list[tuple[str, bytes]], dict[str, list[str]]]`
(`ingest_docbundles.py:207`) — stop and report.

- [ ] **Step 3: Confirm the ingest is the only remaining stripper**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
grep -rn "lstrip\|_split_front_matter\|frontmatter\." \
  apps/backend/app/modules/knowledge/internal/ingest_docbundles.py
```
Expected: no frontmatter handling in `ingest_docbundles.py` today. That absence is what
Step 4 fills; if a strip already exists there, the finding is stale — stop and report.

- [ ] **Step 4: Strip at index time**

In `ingest_docbundles.py`, add to the imports:

```python
from app.modules.knowledge.internal import frontmatter
```

and change the read at `:249` from

```python
            body = page_file.read_text(encoding="utf-8")
```

to

```python
            # O bloco OKF viaja no arquivo (adapt_openwiki) e PARA aqui: o que segue vira o
            # texto indexado, e YAML no corpus faria o modelo citar `generated:` como se fosse
            # conteúdo. `split` não interpreta nada — quem lê METADADO usa `parse` e aceita
            # falhar alto; aqui só se quer o corpo.
            _, body = frontmatter.split(page_file.read_text(encoding="utf-8"))
            body = body.lstrip("\n")
```

Leave the H1-dropping branch and the `f"# {label} — {title}"` header exactly as they are.

- [ ] **Step 5: Run it and confirm it passes**

Run: `cd apps/backend && uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test`
Expected: exit 0, all checks `✓`.

- [ ] **Step 6: Confirm the ingest contract and fidelity are unmoved**

Run:
```bash
cd apps/backend
uv run python -m eval.docbundle_contract_test
uv run python -m eval.wiki_shelf_test
uv run lint-imports --config importlinter.toml
uv run python -m tests.architecture.module_graph_test
```
Expected: all pass. `wiki_shelf_test` reads the committed bundle from disk, so its score
must be **identical** — it measures citations in prose, and the block was never prose.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/app/modules/knowledge/internal/ingest_docbundles.py \
        apps/backend/tests/knowledge/bundle_frontmatter_roundtrip_test.py
git commit -m "feat(okf): strip frontmatter at index time, not at adaptation time"
```

---

# PHASE 4 — Regenerate once, then close every gate

**Target artifacts:** `openwiki/` (written by `openwiki@0.4.3`) and, through the adapter
Phase 3 just fixed, `knowledge/wiki-bundle/`. **No production code changes in this phase**
— one operator action and two gate changes that only become satisfiable after it.

**One dispatch, by your decision.** The workflow costs model credits and opens a pull
request a human must review, so it runs once, here, at the end — with every code change
already in place, so a single regeneration produces artifacts that satisfy Tasks 4.2 and
4.3 without a second run.

---

### Task 4.1: Regenerate `openwiki/` with the pinned generator

**Files:**
- Modify (by regeneration, via pull request): `openwiki/**`
- Read only: `.github/workflows/wiki-regen.yml`

**Interfaces:**
- Produces: an `openwiki/` bundle whose non-reserved pages carry `generated` (and, from
  the generator's own Claims pass, `verified`), and whose root `index.md` declares
  `okf_version: "0.2"`. Task 4.2 depends on the last of these.

**This step requires a human.** `wiki-regen.yml` is `workflow_dispatch` only (line 20), by
ADR-016's decision to look at the pull requests before enabling a cron. It consumes model
credentials and opens a PR. An implementing agent cannot run it.

- [ ] **Step 1: Confirm the pin and the current staleness**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
grep -n "npm install --global openwiki@" .github/workflows/wiki-regen.yml
cat openwiki/.last-update.json
head -3 openwiki/index.md
grep -c "^generated:" openwiki/backend/*.md || true
```
Expected: the pin is `openwiki@0.4.3`; `.last-update.json` shows `2026-08-19` (older than
the 2026-08-27 bump recorded at `wiki-regen.yml:68`); `index.md` declares
`okf_version: "0.1"`; **zero** pages carry `generated`.

If the pages already carry `generated`, the regeneration already happened — skip to
Step 4.

- [ ] **Step 1b: PUSH THE BRANCH FIRST — the workflow cannot see an unpushed ref**

`wiki-regen.yml` runs on GitHub Actions against a ref GitHub can resolve. Verify, and stop
if either line is empty:

```bash
cd "$(git rev-parse --show-toplevel)"
git remote -v
git ls-remote --heads origin "$(git branch --show-current)"
```

Found in execution on 2026-09-02: neither this branch nor its base existed on `origin`, so
"Run workflow" would not have listed them. The plan had gone straight to dispatch.

Pushing is the owner's call, not the implementer's — it publishes every commit on the
branch, including any the base branch carries that were never pushed either. Ask, then push
what the owner authorises.

Two further preconditions the workflow needs, checkable only on GitHub:
`vars.OPENWIKI_BASE_URL`, `vars.OPENWIKI_MODEL`, `secrets.OPENWIKI_API_KEY`.

- [ ] **Step 2: Ask the operator to dispatch the workflow**

Report to the user, and wait:

> Run **Actions → Wiki regen → Run workflow**, selecting this branch (it must appear in
> the ref list — if it does not, Step 1b did not happen), with `force: true` and
> `rebuild: false`. It installs `openwiki@0.4.3`, regenerates `openwiki/`, adapts it into
> `knowledge/wiki-bundle/` **using this branch's `adapt_openwiki`**, which is why Phase 3
> lands first. It then runs the fidelity gate and opens a pull request from `wiki/regen`.
> `peter-evans/create-pull-request` bases that PR on the checked-out branch by default —
> confirm on the run that it targets this branch and not `main`. Merge it here before
> Task 4.2.
>
> Note the run is not additive: a prune step deletes every bundle version that is not the
> one just produced, so `v0.20260819` is replaced rather than joined.

- [ ] **Step 3: Verify what came back**

After the PR lands, run:
```bash
cd "$(git rev-parse --show-toplevel)"
echo "-- páginas sem generated (esperado: vazio):"
grep -rL "^generated:" openwiki --include='*.md' | grep -v 'index\.md$' || true
echo "-- versão declarada:"; sed -n '1,3p' openwiki/index.md
echo "-- verified escrito pelo gerador:"; grep -rl "^verified:" openwiki --include='*.md' | wc -l
cd apps/backend && uv run --with pyyaml --no-project python vendor/okf_validate.py ../../openwiki --json \
  | python3 -c "import json,sys; r=json.load(sys.stdin); print('conformant:', r['conformant'], '| errors:', len(r['errors']), '| warnings:', len(r['warnings']))"
```
Expected: the first command prints nothing (`INSTRUCTIONS.md` may appear — it is
user-authored input, not generator output; if it does, record that and continue);
`okf_version: "0.2"`; a non-zero count of pages carrying `verified`; the validator
reporting `conformant: True`, `errors: 0`, and **no** `§12` version warning.

**If `okf_version` is still `"0.1"`, stop and report.** Task 4.2 must not be forced by
hand-editing the file — that would restore the false claim in the other direction.

- [ ] **Step 4: Record the measurement in the findings**

In `docs/OKF-CONFORMANCE-FINDINGS.md`, append a dated line under §5 gap **G2** and under
§7 defect **2** stating that both closed by regeneration with `openwiki@0.4.3`, naming the
PR. **Leave the original measurements intact** — the report is a historical record, not a
status board.

- [ ] **Step 5: Commit**

```bash
git add docs/OKF-CONFORMANCE-FINDINGS.md
git commit -m "docs(okf): record that G2 and defect 2 closed by regeneration at 0.4.3"
```

---

### Task 4.2: Treat an `okf_version` mismatch as a gate error

**Precondition:** Task 4.1 verified `okf_version: "0.2"` in `openwiki/index.md`.

**Files:**
- Modify: `apps/backend/tests/knowledge/okf_conformance_test.py` (pass/fail branch)
- Read only: `apps/backend/vendor/okf_validate.py:331-334`

**Interfaces:**
- Consumes: `BUNDLES`, `EXCLUDED_BUNDLES` (Task 1.2).
- Produces: a gate that exits non-zero if any measured bundle declares a version other
  than the one the validator checked against.

**Rationale:** the validator is right to call this a warning — the spec says a consumer
should attempt best-effort consumption of an unknown declared version (`SPEC.md:778-780`).
The *gate* is what decides severity for our own bundles, and a bundle of ours claiming a
version we do not validate against is a false claim, not best-effort consumption.
`vendor/okf_validate.py` is not edited (global constraint).

- [ ] **Step 1: Confirm the warning text and the current branch**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -n '328,336p' apps/backend/vendor/okf_validate.py
sed -n '86,96p' apps/backend/tests/knowledge/okf_conformance_test.py
```
Expected: a `report.warn` whose message contains `§12` and `okf_version`; a gate branch
computing `ok` from `rel.get("conformant")` and `errors` only.

- [ ] **Step 2: Promote the warning**

In `okf_conformance_test.py`, add beside the other module constants:

```python
#: Avisos que ESTE gate trata como erro. A spec manda o consumidor tentar consumir um bundle
#: de versão desconhecida (SPEC.md:778-780) — e por isso o verificador está certo em avisar.
#: Mas um bundle NOSSO declarando uma versão que não validamos não é consumo best-effort, é
#: uma afirmação falsa; foi assim que `okf_version: "0.1"` sobreviveu a todo merge desde que
#: o gate existe. O verificador é de terceiro e não se edita (vendor/README.md).
AVISOS_FATAIS = ("okf_version",)
```

Replace the `ok` computation with:

```python
        erros = rel.get("errors", [])
        avisos = rel.get("warnings", [])
        promovidos = [a for a in avisos if any(t in a for t in AVISOS_FATAIS)]
        ok = bool(rel.get("conformant")) and not erros and not promovidos
        print(f"  {'✓' if ok else '✗'} {nome}: {len(erros)} erro(s) · "
              f"{len(avisos)} aviso(s) · {len(promovidos)} aviso(s) fatal(is)")
        for e in erros[:10]:
            print(f"      ✗ {e}")
        for a in promovidos:
            print(f"      ✗ (aviso promovido a erro) {a}")
```

- [ ] **Step 3: Run the gate**

Run: `cd apps/backend && uv run python -m tests.knowledge.okf_conformance_test`
Expected: **exit 0**, four bundles `✓`, `0 aviso(s) fatal(is)` on each, the exclusions
still printed. If `openwiki` shows a fatal warning, Task 4.1 did not land — go back.

- [ ] **Step 4: Prove the gate would catch a regression**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -i.bak 's/okf_version: "0.2"/okf_version: "0.1"/' openwiki/index.md
(cd apps/backend && uv run python -m tests.knowledge.okf_conformance_test); echo "exit=$?"
mv openwiki/index.md.bak openwiki/index.md
git diff --quiet openwiki/index.md && echo "restaurado ok"
```
Expected: `exit=1` with the promoted warning printed, then `restaurado ok`.
**Do not commit the temporary edit.**

- [ ] **Step 5: Commit**

```bash
git add apps/backend/tests/knowledge/okf_conformance_test.py
git commit -m "fix(okf): gate fails on okf_version mismatch instead of warning"
```

---

### Task 4.3: `wiki-bundle` joins the conformance gate

**Precondition:** Task 4.1's regeneration pull request merged. Because Phase 3 landed
first, that single run wrote `knowledge/wiki-bundle/**` through an adapter that already
preserves the block — no second dispatch and no local adapter re-run is needed.

**Files:**
- Modify: `apps/backend/tests/knowledge/okf_conformance_test.py` (`BUNDLES`,
  `EXCLUDED_BUNDLES`)

**Interfaces:**
- Consumes: `BUNDLES`, `EXCLUDED_BUNDLES` (1.2), `AVISOS_FATAIS` (3.2).
- Produces: the gate measures the artifact the `selfwiki` domain queries. Closes audit
  defect 1 and gap G1.

- [ ] **Step 1: Confirm the committed bundle now has frontmatter**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
ls knowledge/wiki-bundle/foundry-assured/
for f in knowledge/wiki-bundle/foundry-assured/*/pages/*.md; do
  head -1 "$f" | grep -q '^---$' || echo "SEM frontmatter: $f"
done; echo "(fim)"
```
Expected: only `(fim)`. Every listed file is a page that would fail §11.1 — if any appear,
regenerate before continuing.

- [ ] **Step 2: Validate it by hand first**

Run:
```bash
cd apps/backend
for d in ../../knowledge/wiki-bundle/foundry-assured/*/; do
  echo "== $d"
  uv run --with pyyaml --no-project python vendor/okf_validate.py "$d" --json \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print(' conformant:', r['conformant'], '| errors:', len(r['errors'])); [print('  ✗', e) for e in r['errors'][:5]]"
done
```
Expected: `conformant: True`, `errors: 0` for every version directory.

**If `type` is missing**, the generator did not write one for those pages. Report it — the
fix belongs upstream in `adapt_openwiki` (lifting `type` from the source page), not in a
hand edit of the bundle.

- [ ] **Step 3: Move the entry**

In `okf_conformance_test.py`:
- Delete the `"knowledge/wiki-bundle"` entry from `EXCLUDED_BUNDLES`.
- Add to `BUNDLES`, keeping the commented style of its neighbours:
  ```python
      # O bundle que o domínio `selfwiki` consulta. Ficou fora deste gate até 2026-09 porque a
      # adaptação retirava o frontmatter (auditoria, defeito 1) — o único artefato não medido,
      # e o único que usuários de fato leem. Uma versão por diretório; todas são cobradas.
      "knowledge/wiki-bundle": REPO / "knowledge" / "wiki-bundle",
  ```

**Note:** `knowledge/wiki-bundle` contains `<component>/<version>/` subdirectories, so the
validator walks several bundles as one tree. That is correct here — every `.md` under it is
a concept and must conform. If the validator's root-`index.md` handling misreports because
there is no root `index.md`, record it and validate each version directory separately by
extending `BUNDLES` with one entry per version instead.

- [ ] **Step 4: Run the gate**

Run: `cd apps/backend && uv run python -m tests.knowledge.okf_conformance_test`
Expected: exit 0; five bundles measured, named in the success line; two exclusions
remaining (`guardrails`, `personas`) with reasons.

- [ ] **Step 5: Close the findings**

In `docs/OKF-CONFORMANCE-FINDINGS.md`, append dated lines marking §7 defect 1, gap G1 and
open question Q1 as closed, naming the commits. Record that Q1 dissolved rather than being
answered: no sidecar was needed, because the schema never governed page content. Leave the
original measurements intact.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/tests/knowledge/okf_conformance_test.py \
        docs/OKF-CONFORMANCE-FINDINGS.md
git commit -m "feat(okf): the bundle selfwiki queries joins the conformance gate"
```

---

# 🛑 GATE C — DECISION REQUIRED BEFORE ANY SEARCH-INDEX WORK

**This plan ends here. Do not start index work without an explicit answer.**

Everything above changes what the artifacts *carry*. Nothing above changes what the search
index *stores* or how retrieval *filters* — today the index holds body text only
(`retrieval.py:317` selects `snippet,blob_url`), so §11 conformance of `wiki-bundle`
changes no answer a user receives.

### The question

Should `type`, `tags` and `status` be projected into the Azure AI Search index as
filterable fields, to allow a deterministic pre-filter before agentic retrieval?

### What makes it a decision and not a task

- It requires an **index rebuild**, sequenced against `acl_setup.py`, which is an
  operational step with a window.
- The pre-filter is **security-critical**. Any filter must be ANDed with
  `permissionFilter` (`acl_setup.py:125`), never substituted for it. A filter that can
  widen a result set for any caller is a security defect, not a bug — and the test for it
  must include a caller entitled to nothing.
- The payoff is **unmeasured**. The stated benefit (cheaper lookups than open-ended
  agentic search) is upstream's claim, not our measurement. It should be a before/after
  number on a fixed question set, and "the number did not move" is a finding worth
  recording rather than a failure to hide.

### What to report before asking

The current `reasoning_effort` baseline from `eval/assurance.yaml:29-32` (measured:
minimal 6/12 · low 7/12 · medium 8/12 on the MCP-enumeration golden), so the pre-filter's
payoff is measured against a number that already exists.

---

# Explicitly NOT in this plan

Recorded so a later reader knows these were considered and declined, not forgotten.

- **`log.md` generation (audit G4, Q3).** Optional per `SPEC.md:535`. OpenWiki does not
  generate one either — it only reserves the name (`src/okf/index-sync.ts:15-16`; no writer
  exists at clone `64903f9`), so adopting it would not supply one. Git history plus the
  manifest already cover the need.
- **`sources[]`, on our side (G7, and the `sources` half of G2).** `_CITE_RE`
  (`wiki_builder.py:98`) makes `:line` optional, and **0 of 676** citations in the ingested
  bundle carry one. Formalizing per-claim provenance for a citation format we measure but
  do not enforce would standardize an empty set. Revisit if the fidelity gate starts
  requiring line ranges. Note this is a decision about *our* producer only: OpenWiki 0.4.3
  writes `sources` into `openwiki/` on its own (`wiki-regen.yml:74`), so that half of G2
  arrives with Task 3.1 without anything being built here — and Task 4.1 is what keeps it
  from being thrown away.
- **`stale_after` and `status` on generated pages (G8).** Freshness is tracked outside the
  documents (`openwiki/.last-update.json`, `eval/wiki_freshness_test.py`) and works.
- **`Attested Computation` (G9).** The attester half maps onto the eval gates
  (`eval/assertions.py`, `eval/wiki_fidelity_test.py:85-100`); the executor and receipt
  halves do not exist. Building them is a product decision about publishing the assurance
  mechanism to third parties, not an OKF conformance task.
- **`docs/` conformance.** The 60 §11.1 errors there are measured against a different
  contract (`DOCS-STANDARD.md:34-46`). Only the one unparseable block (Task 0.1) is in
  scope, because it would crash ingest.
- **Adopting OpenWiki as *the* pipeline (audit Q2).** Independent decision. Three producers
  exist and the fidelity gate is producer-agnostic by construction. This plan consumes the
  generator that is already pinned; it does not retire the other two.
- **Audit Q7** — whether the OKF spec repository was formally moved out of
  `knowledge-catalog`. Task 0.2 settles the citation by pointing at the repository that
  self-describes as canonical (`README.md:5-6`) and pinning its commit. The provenance
  question itself is left open and does not block anything.

---

# Flagged separately: the dormant `groups:` path

**Not part of this plan. Raise it; do not touch it.**

`frontmatter.py:60` reads a `groups:` key that becomes the Azure AI Search
`permissionFilter` (`ingest.py:167-177`, `acl_setup.py:125`, ADR-031). It is fail-closed in
both directions and correctly designed. But `grep -rn "^groups:"` across every `.md` in the
repository returns nothing, while live ACLs come from a gitignored `ACL_CLASSIFICATION`
JSON (`acl_setup.py:71-77`).

Security-relevant code that no committed content exercises rots: nobody tests the path, and
it wakes up on some future deploy. Either exercise it with a fixture or remove it. This is
independent of OKF and plausibly more urgent than Gate C.

---

# Rollback

- **Phase 0:** revert the commits. No generated artifact changed.
- **Phase 1:** revert the commits. `actors.py` has no callers until Phase 2.
- **Phase 2:** revert the commits, then re-record the module graph
  (`uv run python -m tests.architecture.module_graph_test --update`) to drop the
  `knowledge → okf` edge. No committed artifact changes, because `wiki_builder` did not
  produce any of them.
- **Phase 3:** revert 3.2 and 3.1 **together**. Reverting 3.1 alone is safe; reverting 3.2
  alone would leave the adapter preserving a block that nothing strips, putting YAML into
  the retrieval corpus on the next ingest. If an ingest already ran, re-ingest after the
  revert.
- **Phase 4:** revert 4.3, then 4.2, then — only if you must — 4.1, which means reverting
  the regeneration pull request. That restores `okf_version: "0.1"` and strips the trust
  family from both artifacts, so 4.2 must be reverted with it or the gate stays red.

---

# Definition of done

Phases 0–4 are complete when all of the following hold. Each is a command with an expected
result, not a judgement.

- [ ] `uv run --project apps/backend --no-sync python scripts/gates.py` exits **zero**, and
      `--list` shows the four gates added by this plan
      (`frontmatter_parseavel_test`, `actors_test`, `wiki_frontmatter_test`,
      `bundle_frontmatter_roundtrip_test`).
- [ ] `uv run python -m tests.knowledge.okf_conformance_test` exits zero, names the five
      bundles it measured, and prints the two it deliberately does not.
- [ ] `grep -rL "^generated:" openwiki --include='*.md' | grep -v 'index\.md$'` prints
      nothing but, at most, `INSTRUCTIONS.md`.
- [ ] No machine actor claims to be a person. Run, from the repository root:
      ```bash
      uv run --project apps/backend --no-sync python -c "
      import pathlib, re, sys, yaml
      bad = []
      for d in ('openwiki', 'knowledge/wiki-bundle'):
          for md in pathlib.Path(d).rglob('*.md'):
              t = md.read_text(encoding='utf-8', errors='replace')
              m = re.match(r'\A---\r?\n(.*?)\r?\n---', t, re.S)
              if not m: continue
              try: meta = yaml.safe_load(m.group(1)) or {}
              except yaml.YAMLError: continue
              if not isinstance(meta, dict): continue
              ev = meta.get('verified')
              atores = [(meta.get('generated') or {}).get('by')]
              atores += [e.get('by') for e in ([ev] if isinstance(ev, dict) else (ev or []))]
              bad += [f'{md}: {a}' for a in atores if a and str(a).startswith('human:')]
      print('\n'.join(bad) or 'ok — nenhum ator human: em campo de máquina')
      sys.exit(1 if bad else 0)"
      ```
      Expected: `ok — nenhum ator human: em campo de máquina`, exit 0.
- [ ] `sed -n '2p' openwiki/index.md` shows `okf_version: "0.2"`, and the validator emits
      no `§12` warning.
- [ ] Pages the verifier rewrote carry a `process:wiki-verifier/<model>` entry in `verified`; a
      `--no-verify` run produces pages with **no** `verified` key.
- [ ] `head -1 knowledge/wiki-bundle/foundry-assured/*/pages/*.md` shows `---` for every
      page, and `uv run python -m tests.knowledge.bundle_frontmatter_roundtrip_test` proves
      none of it reaches the index.
- [ ] `git diff main -- apps/backend/app/modules/knowledge/internal/frontmatter.py` is
      **empty**, and `git diff main -- apps/backend/app/modules/knowledge/internal/acl_setup.py`
      is **empty**.
- [ ] `git diff main -- apps/backend/vendor/` is **empty**.
- [ ] `uv run python -m eval.wiki_shelf_test` passes with the **same** fidelity score as
      before Phase 2.
- [ ] `docs/OKF-CONFORMANCE-FINDINGS.md` records which gaps and defects closed and by which
      commit, with its original measurements unedited.
- [ ] Gate C has been reported, whether or not it is answered.
