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

import app as _app

APP = pathlib.Path(_app.__file__).resolve().parent
FIXTURE = pathlib.Path(__file__).with_name("module_graph.json")

# ADR-017's file → module map. Prefix rules cover the directories that move wholesale.
# Only the composition root is listed by name; every business file lives under
# `modules/<name>/` and is derived by the prefix rule below. Phase 3 is what made this short.
MAP: dict[str, str] = {
    "main.py": "COMPOSITION",
    "registry.py": "COMPOSITION",
    "api_health.py": "COMPOSITION",
}

# Every business module lives at `modules/<name>/`, so its name IS the mapping. Listed
# explicitly rather than globbed so that a typo in a directory name fails the run instead of
# silently inventing a module.
MODULES = (
    "tenancy", "admin", "knowledge", "helpdesk", "grounded",
    "platform_ops", "tickets", "hosted", "evaluation", "agentdefs",
    "oncall",  # ADR-020: the LangGraph domain — a different runtime, same guarantees
    # Gêmeo do oncall no harness deepagents. Existe para MEDIR a diferença entre os dois, não
    # para substituir: mesmas tools, mesmo prompt, mesmo contrato de HITL.
    "deepcall",
    # A camada de negócio sobre os agentes: casos de uso são LEITURA sobre o registry, os agentes
    # publicados e os fluxos — não uma tabela nova (SEGUNDA MÁXIMA).
    "usecases",
    # Recursos do Foundry (agentes, e depois bases e skills) expostos ao usuário final. Fino
    # por construção: a gestão é do SDK, aqui mora projeção e autorização.
    "foundry",
    # Os FORMULÁRIOS do produto como documento (`type: formflow` num bundle OKF), em vez de três
    # componentes React com os mesmos campos escritos à mão. O módulo só CARREGA e valida a forma;
    # quem aplica as regras é a tela, no campo, e o backend na fronteira.
    "formflow",
    # O contrato canônico dos documentos OKF autoráveis: envelope, identidade, versão e
    # referências. Separado de formflow porque o formulário tolera frontmatter torto para ainda
    # renderizar; publicação e autoria precisam falhar alto.
    "okf",
    "hitl",  # ADR-019: approve/edit/reject/respond + the role gate neither framework has
    # Onde uma conversa fica depois que a aba fecha. O store (blobs de apêndice) e o
    # HistoryProvider do agent-framework; o caminho do blob começa no object-id do usuário, que é
    # o que isola uma pessoa da outra.
    "conversations",
    # ADR-022: rascunha e mostra a otimização do Foundry. NUNCA publica — e isso é
    # verificado por `proposer_read_only_test`, não prometido em comentário.
    "proposer",
    # O assistente do WIZARD (não do chat de domínio). `tool` porque só o caminho do adapter
    # repassa a tool de frontend que ele precisa chamar; sem tools de servidor, ele só propõe.
    "builder",
    # O preço por token, lido da lista pública da Azure (`prices.azure.com`). Módulo próprio e não
    # `shared`: o shared kernel promete não fazer I/O, e este faz chamada de rede. A aritmética de
    # custo continua lá, pura; aqui mora só de onde vem o número.
    "pricing",
    # ADR-023: a camada de EVIDÊNCIA. Trilha encadeada por hash + o redator que roda antes de
    # qualquer gravação. A imutabilidade é do Azure (política WORM no container); o evento é nosso.
    "audit",
    # O CATÁLOGO de domínios (Fase 0c): quais assistentes existem, de que kind, e como cada um
    # está configurado para o tenant da requisição. Saiu de `app/registry.py` porque é dado de
    # negócio, e porque DOIS composition roots o consomem — o monolito e `apps/mcp`.
    "domains",
)

PREFIXES = (
    ("shared/", "shared"),  # incl. shared/telemetry/* — a package whose __init__ has real logic
    *((f"modules/{name}/", name) for name in MODULES),
)

# `__init__.py` files that are pure package markers carry no imports and are not worth a MAP
# entry. One that carries logic IS worth one, so only a marker may be skipped: anything with
# an import statement must be mapped, or the graph would quietly miss its edges.


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
        tree = ast.parse(path.read_text())
        source = module_of(relative)
        if source is None:
            # A package marker may be skipped; an __init__ that imports anything may not, or
            # its edges would vanish from the graph without anyone noticing. Decided from the
            # AST, not from the text: a docstring that merely mentions the word "import" is
            # still a marker.
            imports = any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
            if path.name != "__init__.py" or imports:
                unmapped.append(relative)
            continue

        for node in ast.walk(tree):
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
