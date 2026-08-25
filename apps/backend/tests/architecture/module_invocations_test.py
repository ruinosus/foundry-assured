"""Every `python -m <module>` in a workflow or script must resolve to a real file.

This gate exists because the module refactor (ADR-017) broke four of them and none of the
other five architecture gates could see it — they all read Python, and these live in YAML
and shell:

    .github/workflows/wiki-regen.yml    python -m app.knowledge.adapt_openwiki
    .github/workflows/provision-kb.yml  python -m app.knowledge.ingest
    scripts/bootstrap.sh                python -m app.knowledge.ingest
    scripts/to-markdown.sh              (in prose)

`wiki-regen` is `workflow_dispatch`, so it does not run on a PR: the break only surfaced
when someone dispatched it, hours after the merge. Invariant I-6 in the spec asked for
exactly this ("CI referencing a moved module by path → update the workflow in the same
phase") and it was checked by grepping for `eval.*`, which missed every `app.*`.

Resolution is by FILE PATH, not `importlib.find_spec`: importing `app.modules.agentdefs`
composes the prompts as a side effect, and a gate should not need the app to boot.

    uv run python -m tests.architecture.module_invocations_test
"""

from __future__ import annotations

import pathlib
import re
import sys

import app as _app

BACKEND = pathlib.Path(_app.__file__).resolve().parent.parent
REPO = BACKEND.parents[1]

# Top-level packages this gate owns. A dotted name whose head is not here belongs to someone
# else (`python -m pip`) and is not this gate's business.
ROOTS = ("app", "eval", "cli", "tests")

# Every app a workflow step may run FROM. The gate used to assume one — apps/backend — because
# there was only one; `apps/mcp` (ADR-027) made that assumption wrong, and the symptom was this
# gate calling five real modules non-existent because it looked for `tests/auth_test.py` under
# the wrong app.
#
# Resolution is against ANY of them, not against the step's actual `working-directory`. That is
# deliberately looser than the truth: reading the job's workdir would mean parsing the YAML
# structure, and the cost is a false NEGATIVE only in one narrow case — a backend-only module
# that happens to share a name with one in apps/mcp. The failure this gate exists to catch (a
# module that moved and now exists NOWHERE) is caught either way.
APPS = (BACKEND, REPO / "apps" / "mcp")

# Files that actually invoke things. Docs are excluded on purpose: a stale command in a
# historical plan is wrong but harmless, while a stale one here fails a real run.
SOURCES = (
    *sorted((REPO / ".github" / "workflows").glob("*.yml")),
    *sorted((REPO / "scripts").glob("*.sh")),
)

# No trailing dot: `app.knowledge.*` in prose must not read as the module `app.knowledge.`.
INVOCATION = re.compile(r"python\s+-m\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)")


def resolves(dotted: str) -> bool:
    """True when `dotted` maps to a real module file or package under any app in `APPS`."""
    head, *rest = dotted.split(".")
    if head not in ROOTS:
        return True  # not ours (e.g. `python -m pip`) — not this gate's business
    for app_root in APPS:
        base = app_root / head
        target = base.joinpath(*rest) if rest else base
        if target.with_suffix(".py").is_file() or (target / "__init__.py").is_file():
            return True
    return False


def main() -> int:
    broken: list[tuple[str, int, str]] = []
    checked = 0

    for path in SOURCES:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            # Comments are prose, and prose is allowed to name a module that moved — only a
            # line that RUNS something can break a workflow.
            if line.lstrip().startswith("#"):
                continue
            for dotted in INVOCATION.findall(line):
                if dotted.split(".")[0] not in ROOTS:
                    continue
                checked += 1
                if not resolves(dotted):
                    broken.append((str(path.relative_to(REPO)), lineno, dotted))

    for relative, lineno, dotted in broken:
        print(f"  ✗ {relative}:{lineno} — `python -m {dotted}` does not resolve")

    if broken:
        print(
            f"\n❌ {len(broken)} invocation(s) point at a module that does not exist.\n"
            "   A workflow that only runs on dispatch will not tell you until someone\n"
            "   dispatches it. Update the caller in the same commit that moves the module\n"
            "   (invariant I-6)."
        )
        return 1

    print(f"✅ all {checked} `python -m` invocations in workflows and scripts resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
