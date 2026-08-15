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

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

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
    for path in sorted(APP.rglob("*.py")):
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
                    found.append((str(path.relative_to(APP)), node.lineno, index.value))
    return found


def main() -> int:
    found = offenders()
    for relative, line, index in found:
        print(f"  ✗ {relative}:{line} — parents[{index}] counts levels from the file")

    if found:
        print(
            f"\n❌ {len(found)} fragile path anchor(s). Counting `parents[N]` bakes in where the\n"
            "   file happens to live, so the next move breaks it — usually without failing a\n"
            "   test. Anchor on the `app` package instead:\n\n"
            "       import app as _app\n"
            "       BACKEND_ROOT = Path(_app.__file__).resolve().parent.parent\n"
            "       REPO_ROOT = Path(_app.__file__).resolve().parents[3]\n"
        )
        return 1
    print("✅ no path is computed by counting parents[N] from a file's own location.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
