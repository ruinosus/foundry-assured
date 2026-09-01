# Skill Observations

Persistent observations captured during task execution. Status defaults to OPEN.

---

### Observation 1: Inspect generated SDK clients at construction time

**Date:** 2026-08-31
**Session context:** Verifying installed Microsoft SDK capabilities before closing an architecture decision.
**Skill:** sdk-verify
**Type:** internal
**Phase/Area:** Installed package introspection
**Status:** OPEN

**Issue:** Class-level introspection of a generated SDK client reported operation groups such as agents, connections, and toolboxes as absent. The installed source showed that these public attributes are assigned in `__init__`, and existing repository code already exercised them. Relying on `dir(ClientClass)` produced false negatives for generated clients.

**Suggested improvement:** In the installed-package verification step, inspect constructor source or instantiate with a non-executing credential/endpoint before declaring an operation group absent. Triangulate class introspection with generated source and a nearby verified call site, and label absence only after all three agree.

**Principle:** Generated clients often expose operation groups as instance attributes created at construction time; capability verification must inspect the instance construction path, not only the class namespace.

---

### Observation 2: Namespace strict product profiles over permissive external formats

**Date:** 2026-08-31
**Session context:** Adding a strict authoring contract over Open Knowledge Format v0.2.
**Skill:** task-observer
**Type:** internal
**Phase/Area:** Schema design and external standards
**Status:** OPEN

**Issue:** The first authoring envelope reused `okf_version`, `resource`, `lifecycle`, `version`
and provenance fields with product-specific meanings. Local tests passed, but the fields conflicted
with the upstream format: `okf_version` belongs to the root index, `resource` names an underlying
asset, and OKF already defines `status` and `generated`.

**Suggested improvement:** Before extending a permissive external format, map every proposed field
against the upstream specification and existing repository consumers. Preserve upstream fields and
put stricter product metadata in one explicit namespace with its own profile version and API names.
Keep upstream conformance tests separate from product-profile validation.

**Principle:** A strict internal profile may narrow what the product publishes, but it must not
redefine the external format or present itself as a generic validator for that format.

---

### Observation 3: Preserve a dirty index when committing a slice

**Date:** 2026-08-31
**Session context:** Committing Smart Coding slice F03 while unrelated frontend renames were already staged.
**Skill:** sc-executar
**Type:** internal
**Phase/Area:** Step 7, selective commit
**Status:** OPEN

**Issue:** The instruction to stage only files touched by the slice is insufficient when the real
index already contains user changes. A normal `git add` and commit would include those changes;
advancing `HEAD` through an alternate index can also make the real index appear stale and obscure
which shared-file hunks belong to earlier work.

**Suggested improvement:** Extend Step 7 with a dirty-index procedure: record staged paths, create a
temporary index from `HEAD`, add slice-owned files there, apply only owned hunks for shared files,
run cached diff checks, commit through that index, and verify the original staged paths remain.
Require comparison against prior slice commits before including catch-up changes from shared files.

**Principle:** Selective commits must preserve both worktree content and index intent; file-level
staging alone is not safe when unrelated changes are already staged or shared files contain mixed work.

---

### Observation 4: Avoid zsh special names in command runners

**Date:** 2026-08-31
**Session context:** Running a slice Definition of Done through an execution helper on macOS/zsh.
**Skill:** task-observer
**Type:** open-source
**Phase/Area:** Command execution
**Status:** OPEN

**Issue:** A generated zsh wrapper assigned an array to `commands`, which is a special associative
parameter containing executable names. The loop then invoked unrelated system binaries and reported
their failures as project validation failures.

**Suggested improvement:** Execution helpers should avoid shell-reserved and zsh-special parameter
names, prefer direct commands for short sequences, and use a neutral name such as `command_list`
when a loop is necessary. Preserve each requested command and its exit code explicitly.

**Principle:** Shell wrappers are part of the validation boundary; reserved parameter collisions can
turn unrelated host behavior into convincing but false project diagnostics.

---

### Observation 5: Smoke command must declare boot prerequisites

**Date:** 2026-08-31
**Session context:** Executing Smart Coding slice F05 with an offline FastAPI smoke test.
**Skill:** sc-fatiar
**Type:** internal
**Phase/Area:** Executable Definition of Done
**Status:** OPEN

**Issue:** The generated smoke command set only `AUTH_ENABLED=false`, but the composition root
required additional synthetic settings to construct eager clients offline. The command failed before
opening the port even though the implemented behavior was correct.

**Suggested improvement:** When generating a Definition of Done, validate boot commands against the
repository's established offline test environment and declare every required non-secret synthetic
setting. Run the smoke once before freezing the slice.

**Principle:** An executable acceptance criterion must carry its non-secret prerequisites; otherwise
it measures implicit workstation state instead of the changed behavior.

---

### Observation 6: Separate workflow governance from product coupling

**Date:** 2026-09-01
**Session context:** Executing a Smart Coding slice in a Python product explicitly independent from the workflow framework's originating organization.
**Skill:** sc-fatiar
**Type:** internal
**Phase/Area:** Skill selection in slice details
**Status:** OPEN

**Issue:** The slice detail retained a stack-specific validation skill even after the product was
made explicitly independent and the repository stack was confirmed as Python/FastAPI. The detail
needed an exception explaining why none of that skill's branded packages could apply.

**Suggested improvement:** In the skill-selection step, verify both repository stack compatibility
and requested product independence before attaching organization-specific implementation skills.
When only a general principle applies, state it directly in the slice instead of loading an
incompatible package contract and documenting an exception afterward.

**Principle:** A process can govern quality without coupling the delivered product to the process
owner's technology; skill selection must preserve that boundary explicitly.
