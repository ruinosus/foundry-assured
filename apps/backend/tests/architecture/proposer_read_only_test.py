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

PROPOSER = Path(_app.__file__).resolve().parent / "modules" / "proposer"


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
        for no in ast.walk(arvore):
            # `from ... import create_agent_version`
            if isinstance(no, ast.ImportFrom):
                for alias in no.names:
                    if alias.name in PROIBIDAS:
                        achados.append(f"{rel}:{no.lineno} importa {alias.name}")
            # `create_agent_version(...)` ou `foundry.create_agent_version(...)`
            elif isinstance(no, ast.Call):
                fn = no.func
                nome = (
                    fn.id if isinstance(fn, ast.Name)
                    else fn.attr if isinstance(fn, ast.Attribute)
                    else ""
                )
                if nome in PROIBIDAS:
                    achados.append(f"{rel}:{no.lineno} chama {nome}()")

    for a in achados:
        print(f"     ✗ {a}")
    check("nenhuma função de escrita de recurso é importada ou chamada", not achados)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print("   A ADR-022 decidiu que o propositor RASCUNHA e a pessoa publica. Se a decisão")
        print("   mudou, mude a ADR primeiro — este gate é o que a torna real.")
        return 1
    print("\n✅ o propositor não publica nem apaga recurso: nenhuma escrita importada ou chamada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
