"""O ingest não pode declarar nada — tudo deriva dos documentos e do registry.

SEGUNDA MÁXIMA: tudo fica no Foundry; a diferença é quem colocou e como. O que ela proíbe é
manter no código uma lista de recursos que também existem no serviço — duas listas divergem no
primeiro item novo, e a divergência não dá erro: só faz a tela mentir.

ESTE GATE NASCEU DE UMA VIOLAÇÃO MINHA, na mesma tarefa em que a máxima foi enunciada. A primeira
versão de `cli/provision_agents.py` tinha `AGENTS = [...]` com nome, prompt e runtime de cada
agente. Publiquei com ela, reescrevi derivando dos documentos, e três agentes ficaram órfãos no
serviço — `concierge`, `deepcall` e `helpdesk`, nomes que a lista inventava e que nenhum documento
sustenta. Eles não atualizavam quando o prompt mudava, e ninguém teria percebido: apareciam na
tela como qualquer outro.

O gate é offline e verifica a FONTE, não o serviço: se o CLI voltar a declarar nomes, cai aqui.

    uv run python -m tests.foundry.ingest_parity_test
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import app

_BACKEND = Path(app.__file__).resolve().parent.parent
_CLI = _BACKEND / "cli" / "provision_agents.py"
_DOCS = _BACKEND / "agents" / "helpdesk"


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    fonte = _CLI.read_text(encoding="utf-8")

    # O CLI pode ter constantes de mapeamento (exceções nomeadas), mas não uma LISTA de agentes
    # com prompt embutido — que é a forma que a violação teve.
    check(
        "o CLI não declara instruções de agente",
        "INSTRUCTIONS," not in fonte and "_INSTRUCTIONS\n" not in fonte,
    )
    check(
        "o CLI não declara uma lista AGENTS",
        not re.search(r"^AGENTS\s*[:=]", fonte, re.MULTILINE),
    )
    check("o CLI deriva dos documentos", "composed_agents()" in fonte)
    check("o CLI deriva o runtime do registry", "DOMAIN_KINDS" in fonte)

    # Todo documento vira agente: se um existir e o ingest não o alcançar, ele nunca chega ao
    # Foundry — e a tela mostraria menos do que o repositório tem.
    docs = {p.stem for p in _DOCS.glob("*.yaml")} - {"scope"}
    from app.modules.agentdefs.public import composed_agents

    compostos = set(composed_agents())
    faltando = docs - compostos
    check(f"todo documento é composto ({len(compostos)} de {len(docs)})", not faltando)
    if faltando:
        print(f"      sem composição: {', '.join(sorted(faltando))}")

    if falhas:
        print(f"\n❌ {len(falhas)} asserção(ões) falharam.")
        return 1
    print("\n✅ o ingest deriva tudo; nenhuma lista paralela de agentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
