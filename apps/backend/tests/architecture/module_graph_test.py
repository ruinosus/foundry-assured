"""Inter-module dependency graph — pinned before the modules exist (Phase 1).

`import-linter` can only guard boundaries that are already directories. During Phases 1–3
the modules are still a plan, so the same question — *which domain depends on which?* — is
answered here instead: every file under `app/` is assigned to its target module (ADR-017's
map), imports are read from the AST, and the resulting edge set is compared to a fixture.

This is what makes the refactor honest. A `git mv` that quietly adds a cross-module
dependency changes no route, breaks no test, and would land unnoticed; here it shows up as a
new edge with the file that introduced it.

MAP is the single source of truth for "which module does this file belong to", and an
unmapped file fails the run — that is the Phase 1 red gate ("a file with no destination
means stop") expressed as code rather than as a promise.

    uv run python -m tests.architecture.module_graph_test            # verify
    uv run python -m tests.architecture.module_graph_test --show     # print the graph
    uv run python -m tests.architecture.module_graph_test --update   # re-record
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
FIXTURE = pathlib.Path(__file__).with_name("module_graph.json")

# ADR-017's file → module map. Prefix rules cover the directories that move wholesale.
MAP: dict[str, str] = {
    "core/settings.py": "shared",
    "core/auth.py": "shared",
    "core/tenant.py": "tenancy",
    "core/tenant_store.py": "tenancy",
    "core/onboarding.py": "tenancy",
    "api/tenant.py": "tenancy",
    "services/graph.py": "admin",
    "api/admin.py": "admin",
    "api/me.py": "admin",
    "services/retrieval.py": "knowledge",
    "agents/secure_search.py": "knowledge",
    "services/grounded.py": "grounded",
    "agents/cockpit.py": "grounded",
    "agents/selfwiki.py": "grounded",
    "agents/concierge.py": "grounded",
    "agents/per_request.py": "grounded",
    "agents/platform.py": "platform_ops",
    "agents/mcp/registry.py": "platform_ops",
    "agents/mcp/tools.py": "platform_ops",
    "tools/tickets.py": "tickets",
    "api/tickets.py": "tickets",
    "services/hosted.py": "hosted",
    "api/chat.py": "hosted",
    "services/foundry_evals.py": "evaluation",
    "api/evals.py": "evaluation",
    "agents/prompts.py": "agentdefs",
    "agents/definitions.py": "agentdefs",
    "domains.py": "COMPOSITION",
    "main.py": "COMPOSITION",
    "api/health.py": "COMPOSITION",
    "api/__init__.py": "COMPOSITION",
}
PREFIXES = (("knowledge/", "knowledge"), ("workflow/", "helpdesk"))


def module_of(relative: str) -> str | None:
    if relative in MAP:
        return MAP[relative]
    for prefix, module in PREFIXES:
        if relative.startswith(prefix):
            return module
    return None


def build_graph() -> tuple[dict[str, dict[str, list[str]]], list[str]]:
    """Return {source module: {target module: [files that import it]}} and any unmapped files."""
    graph: dict[str, dict[str, set[str]]] = {}
    unmapped: list[str] = []

    for path in sorted(APP.rglob("*.py")):
        relative = str(path.relative_to(APP))
        source = module_of(relative)
        if source is None:
            if path.name != "__init__.py":  # empty package markers carry no imports
                unmapped.append(relative)
            continue

        for node in ast.walk(ast.parse(path.read_text())):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
                targets.append(node.module[len("app.") :])
            elif isinstance(node, ast.Import):
                targets += [a.name[len("app.") :] for a in node.names if a.name.startswith("app.")]

            for dotted in targets:
                slashed = dotted.replace(".", "/")
                target = module_of(f"{slashed}.py") or module_of(f"{slashed}/")
                if target and target != source:
                    graph.setdefault(source, {}).setdefault(target, set()).add(relative)

    return ({s: {t: sorted(f) for t, f in sorted(ts.items())} for s, ts in sorted(graph.items())},
            unmapped)


def main() -> int:
    graph, unmapped = build_graph()

    if unmapped:
        print("❌ files with no module assigned — ADR-017's map is incomplete:")
        for relative in unmapped:
            print(f"     {relative}")
        print("\n   Add each to MAP (or a prefix rule) before moving any code.")
        return 1

    if "--show" in sys.argv:
        for source, targets in graph.items():
            for target, files in targets.items():
                print(f"{source:14s} -> {target:14s}  ({', '.join(files)})")
        return 0

    if "--update" in sys.argv:
        FIXTURE.write_text(json.dumps(graph, indent=2) + "\n")
        edges = sum(len(t) for t in graph.values())
        print(f"✅ recorded {edges} edges across {len(graph)} modules — review the diff.")
        return 0

    if not FIXTURE.exists():
        print(f"❌ {FIXTURE.name} missing. Record it with --update.")
        return 1

    baseline = json.loads(FIXTURE.read_text())
    current = {(s, t) for s, ts in graph.items() for t in ts}
    recorded = {(s, t) for s, ts in baseline.items() for t in ts}

    added, removed = sorted(current - recorded), sorted(recorded - current)
    for source, target in added:
        print(f"  ✗ NEW edge {source} -> {target}  (via {', '.join(graph[source][target])})")
    for source, target in removed:
        print(f"  ✓ edge removed {source} -> {target}")

    if added:
        print(
            f"\n❌ {len(added)} new cross-module dependency/ies. The refactor is supposed to move\n"
            "   code, not create coupling. If the edge is intended, record it with --update and\n"
            "   justify it in ADR-017."
        )
        return 1
    if removed:
        print(f"\n✅ {len(removed)} edge(s) removed, none added — re-record with --update.")
        return 0
    print(f"✅ dependency graph unchanged ({len(current)} edges).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
