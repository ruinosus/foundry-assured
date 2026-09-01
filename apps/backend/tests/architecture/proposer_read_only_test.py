"""O propositor NUNCA publica — verificado, não prometido (ADR-022).

    uv run python -m tests.architecture.proposer_read_only_test

POR QUE ESTE GATE EXISTE. A ADR-022 decidiu que o propositor rascunha e o humano publica. Dito
assim, isso é uma intenção — e o risco real não é alguém discordar da decisão, é uma edição futura
que acrescenta a chamada de publicação "para economizar um clique". Um comentário não impede isso;
um teste que roda a cada push impede.

O QUE É VERIFICADO, por análise do AST e não por busca de texto: nenhuma função de ESCRITA de
recurso é importada ou chamada em `app/modules/proposer/`. Busca por string acharia a palavra
dentro de um comentário e daria falso positivo; e perderia um `getattr(mod, "create_" + x)`. O
AST pega import e chamada, que é onde o risco mora de verdade.

O que NÃO é proibido: `start_optimization`, que cria um JOB no serviço. Job não é recurso
publicado — ele produz candidatos cujo `promotion` nasce nulo, que é justamente a fronteira que
esta ADR preserva. A rota que o dispara exige Admin.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import app as _app

#: As funções que PUBLICAM ou APAGAM recurso. Nenhuma pode aparecer no propositor.
PROIBIDAS = {
    "create_agent_version",
    "create_knowledge",
    "create_skill",
    "create_skill_from_files",
    "create_toolbox_version",
    "import_skill",
    "delete_agent",
    "delete_knowledge",
    "delete_skill",
    "delete_toolbox",
    "set_agent_enabled",
    "upload_files",
    "ingest_repo",
    "save_flow",
}

COLECOES_DE_RECURSOS = {"agents", "knowledge", "skills", "toolboxes"}
METODOS_DE_ESCRITA = {"create", "create_version", "delete", "update", "upload"}

PROPOSER = Path(_app.__file__).resolve().parent / "modules" / "proposer"


def _attribute_chain(node: ast.expr) -> list[str]:
    chain: list[str] = []
    while isinstance(node, ast.Attribute):
        chain.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        chain.append(node.id)
    return list(reversed(chain))


def _write_findings(tree: ast.AST, where: str) -> list[str]:
    findings: list[str] = []
    collection_aliases = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and COLECOES_DE_RECURSOS & set(_attribute_chain(node.value))
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in PROIBIDAS:
                    findings.append(f"{where}:{node.lineno} importa {alias.name}")
        elif isinstance(node, ast.Attribute):
            chain = _attribute_chain(node)
            if (
                chain
                and chain[-1] in METODOS_DE_ESCRITA
                and (COLECOES_DE_RECURSOS | collection_aliases) & set(chain[:-1])
            ):
                findings.append(
                    f"{where}:{node.lineno} referencia escrita oficial {'.'.join(chain)}"
                )
        elif isinstance(node, ast.Call):
            function = node.func
            name = (
                function.id if isinstance(function, ast.Name)
                else function.attr if isinstance(function, ast.Attribute)
                else ""
            )
            if name in PROIBIDAS:
                findings.append(f"{where}:{node.lineno} chama {name}()")
            if (
                isinstance(function, ast.Name)
                and function.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in METODOS_DE_ESCRITA
                and (COLECOES_DE_RECURSOS | collection_aliases)
                & set(_attribute_chain(node.args[0]))
            ):
                findings.append(f"{where}:{node.lineno} obtém escrita oficial via getattr")
    return findings


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    check("o módulo proposer existe", PROPOSER.is_dir())
    if not PROPOSER.is_dir():
        print("\n❌ módulo ausente.")
        return 1

    arquivos = sorted(PROPOSER.rglob("*.py"))
    check("há código para inspecionar", len(arquivos) > 0)

    achados: list[str] = []
    for arq in arquivos:
        arvore = ast.parse(arq.read_text(encoding="utf-8"), filename=str(arq))
        rel = arq.relative_to(PROPOSER.parent.parent)
        achados.extend(_write_findings(arvore, str(rel)))

    for a in achados:
        print(f"     ✗ {a}")
    check("nenhuma função de escrita de recurso é importada ou chamada", not achados)
    direct = ast.parse("import azure.ai.projects as projects\nclient.agents.create_version({})")
    aliased = ast.parse("agents = client.agents\nagents.create_version({})")
    indirect = ast.parse('getattr(client.toolboxes, "delete")("name")')
    read_only = ast.parse("client.responses.create(model='gpt')\nclient.agents.list()")
    check("escrita oficial direta é detectada", bool(_write_findings(direct, "fixture")))
    check("escrita oficial por alias é detectada", bool(_write_findings(aliased, "fixture")))
    check("escrita oficial via getattr é detectada", bool(_write_findings(indirect, "fixture")))
    check("chamadas de inferência e leitura continuam permitidas", not _write_findings(read_only, "fixture"))

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print("   A ADR-022 decidiu que o propositor RASCUNHA e a pessoa publica. Se a decisão")
        print("   mudou, mude a ADR primeiro — este gate é o que a torna real.")
        return 1
    print("\n✅ o propositor não publica nem apaga recurso: nenhuma escrita importada ou chamada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
