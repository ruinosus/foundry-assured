"""No path may be computed by counting `parents[N]` from a file's own location.

This gate exists because the refactor already broke three of them, silently:

  - `prompts.py` resolved the AgentSchema documents with `parents[2]`. Moving it to
    `modules/agentdefs/` made that `app/agents`, which does not exist. This one at least
    failed loudly at boot.
  - `wiki_builder` read `parents[2]/eval/assurance.yaml` — became `app/modules/eval/...`.
  - `ingest_docbundles` read `parents[4]/docs/wiki` — became `apps/backend/docs/wiki`.

The last two broke in **silence**. Nothing pointed at them: the tests that exercise those
paths were already failing for unrelated reasons, so a green suite proved nothing. That is
the failure mode this whole refactor has to be defended against — a condition that was true
only by accident of where a file happened to sit.

The fix in every case is to anchor on the `app` package, which does not move relative to the
repository. This test forbids the fragile form outright, so the next `git mv` cannot
reintroduce it.

    uv run python -m tests.architecture.filesystem_anchors_test
"""

from __future__ import annotations

import ast
import pathlib
import sys

import app as _app

BACKEND = pathlib.Path(_app.__file__).resolve().parent.parent
# app/ AND the test trees: hosted_platform_smoke_test broke the same way when it moved from
# eval/ to tests/hosted/, so scanning only app/ was scanning half the problem.
ROOTS = (BACKEND / "app", BACKEND / "tests", BACKEND / "eval")

# `parents[0]` and `parents[1]` are a file's own directory and its parent — those stay local
# to the module and survive a move of the module as a whole. Anything deeper is reaching
# across the layout and is what breaks.
MAX_SAFE_DEPTH = 1


def _rooted_in_own_file(node: ast.AST) -> bool:
    """True when the `.parents` chain starts from a bare `__file__` (not `<pkg>.__file__`)."""
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr == "__file__":
            return False  # something.__file__ — an anchored package reference
        if isinstance(child, ast.Name) and child.id == "__file__":
            return True
    return False


def offenders() -> list[tuple[str, int, int]]:
    """(relative path, line, index) for every `.parents[N]` with N > MAX_SAFE_DEPTH."""
    found: list[tuple[str, int, int]] = []
    for path in sorted(p for root in ROOTS for p in root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)):
                continue
            if node.value.attr != "parents":
                continue
            # `Path(_app.__file__)...parents[N]` IS the anchored form this test asks for —
            # it counts from the `app` package, which does not move. Only a chain rooted in
            # this file's own `__file__` is fragile.
            if not _rooted_in_own_file(node.value):
                continue
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, int):
                if index.value > MAX_SAFE_DEPTH:
                    found.append((str(path.relative_to(BACKEND)), node.lineno, index.value))
    return found


# --- Second rule: a path built from literal segments must actually EXIST -------------------
#
# Counting depth was only half the problem. `ingest.py` used `Path(__file__).parent / "corpus"`
# — depth 0, which the rule above deliberately allows — and it still broke: ADR-017 moved the
# module into `internal/` while `corpus/` stayed put, so the path pointed at `internal/corpus`,
# which does not exist. Ingestion exited with "No markdown found" and every gate stayed green.
#
# Two more were hiding behind the same blind spot: `eval/assertions.py` still read
# `app/knowledge/corpus` (the pre-ADR-017 layout) and `wiki_builder` read `internal/skills`.
#
# So the check that matters is not how the path is spelled, it is whether it LANDS. Resolve
# every statically-known path and require the target to exist. This says nothing about style —
# `Path(__file__).parent / "x"` stays legal when `x` is genuinely there.
_RUNTIME_SUFFIXES = (".jsonl", ".json", ".log", ".yaml.lock")


def _literal_segments(node: ast.AST) -> list[str] | None:
    """The trailing literal path segments of a `<base> / "a" / "b"` chain, innermost first."""
    segments: list[str] = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
            return None
        segments.insert(0, node.right.value)
        node = node.left
    return segments or None


def _resolve_base(node: ast.AST, path: pathlib.Path) -> pathlib.Path | None:
    """The directory a `Path(__file__)` / `Path(<pkg>.__file__)` base with `.parent`s denotes."""
    attrs: list[str] = []
    while isinstance(node, ast.Attribute):
        attrs.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return None
    if node.func.id != "Path" or not node.args:
        return None

    arg = node.args[0]
    if isinstance(arg, ast.Name) and arg.id == "__file__":
        base = path
    elif isinstance(arg, ast.Attribute) and arg.attr == "__file__":
        base = pathlib.Path(_app.__file__).resolve()  # the anchored form
    else:
        return None

    for attr in attrs:  # `.resolve()` is a Call, so it never lands here; only `.parent` does
        if attr == "parent":
            base = base.parent
    return base


def dangling() -> list[tuple[str, int, str]]:
    """(relative path, line, resolved target) for literal paths that do not exist."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(p for root in ROOTS for p in root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
                continue
            segments = _literal_segments(node)
            if not segments:
                continue
            # Walk to the innermost left operand — the base of the `/` chain.
            base_node = node
            while isinstance(base_node, ast.BinOp):
                base_node = base_node.left
            base = _resolve_base(base_node, path.resolve())
            if base is None:
                continue
            target = base.joinpath(*segments)
            # A file the app WRITES need not exist yet; its directory must.
            probe = target.parent if target.suffix in _RUNTIME_SUFFIXES else target
            if not probe.exists():
                found.append((str(path.relative_to(BACKEND)), node.lineno, str(target)))
    return found


def main() -> int:
    found = offenders()
    for relative, line, index in found:
        print(f"  ✗ {relative}:{line} — parents[{index}] counts levels from the file")

    missing = dangling()
    for relative, line, target in missing:
        print(f"  ✗ {relative}:{line} — path does not exist: {target}")

    if missing and not found:
        print(
            f"\n❌ {len(missing)} path(s) point at nothing. A path that resolves to a missing\n"
            "   directory fails at RUN time, not at import time, so the suite stays green while\n"
            "   the feature is dead. Anchor on the `app` package and point at what is there:\n\n"
            "       import app as _app\n"
            "       CORPUS = Path(_app.__file__).resolve().parent / 'modules' / 'knowledge' / 'corpus'\n"
        )
        return 1

    if found or missing:
        print(
            f"\n❌ {len(found)} fragile path anchor(s). Counting `parents[N]` bakes in where the\n"
            "   file happens to live, so the next move breaks it — usually without failing a\n"
            "   test. Anchor on the `app` package instead:\n\n"
            "       import app as _app\n"
            "       BACKEND_ROOT = Path(_app.__file__).resolve().parent.parent\n"
            "       REPO_ROOT = Path(_app.__file__).resolve().parents[3]\n"
        )
        return 1
    print(
        "✅ no path counts parents[N] from a file's own location, and every statically-known\n"
        "   path lands on something that exists."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
