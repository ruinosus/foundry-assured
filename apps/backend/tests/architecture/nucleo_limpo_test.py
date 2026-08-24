"""Núcleo limpo: quem só lê a KB não deve puxar framework de agente.

Uma medição mostrou que a maioria dos módulos deste backend já não importa
`agent_framework`/`langchain`/`langgraph`/`deepagents` — consequência não planejada das
fronteiras da ADR-017, não de decisão explícita. Dois módulos ainda puxavam framework por
motivo pequeno: `tickets` construía, no import, uma tool de agent-framework que nenhum
consumidor usava; `hitl` reexportava no topo do arquivo um adaptador de LangGraph que só
`oncall`/`deepcall` chamam. Os dois foram limpos — este teste é o que prova que continuam
limpos, e o que acusa se algum PR futuro trouxer a dependência de volta.

POR QUE SUBPROCESSO, e não `importlib.import_module` direto no processo do teste: uma vez que
um módulo entra em `sys.modules`, ele fica — importar `tickets.public` DEPOIS de importar
`hitl.public` no mesmo processo herdaria `langchain` de `sys.modules` mesmo que `tickets` não o
importe, e o teste passaria por acidente. Cada módulo entra num processo Python novo, então só
o que ELE importa aparece.

POR QUE ISTO É COMPLEMENTAR ao contrato `forbidden` do `importlinter.toml` ("núcleo limpo: sem
framework de agente"), não redundante: o `import-linter` prova o grafo ESTÁTICO — útil e rápido,
mas cego a quando um import roda. `hitl.public` mantém de propósito um import PREGUIÇOSO (dentro
da função `recording_hitl`, só executado quando `oncall`/`deepcall` chamam) que alcança
LangChain — o `import-linter` vê essa aresta e não tem como saber que ela só roda sob chamada,
não no import a frio. Por isso `hitl` fica fora do contrato estático e só este teste, que importa
de verdade, prova que `import hitl.public` sozinho não carrega LangChain.

O QUE QUEBRA SE ISTO REGREDIR: a dependência de framework de agente volta a ser obrigatória para
quem só quer ler a base de conhecimento, abrir um chamado, decidir uma aprovação, checar um papel
ou consultar a trilha — fechando a porta que este núcleo limpo abre para um app separado
(ADR-027) sem levar `agent_framework`/`langchain`/`langgraph`/`deepagents` junto.

    uv run python -m tests.architecture.nucleo_limpo_test
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import app as _app

BACKEND = Path(_app.__file__).resolve().parent.parent

#: Os quatro pacotes pesados de framework de agente. Qualquer um em `sys.modules` depois do
#: import do módulo é uma regressão.
FRAMEWORKS = ("agent_framework", "langchain", "langgraph", "deepagents")

#: O núcleo limpo: os módulos cuja superfície pública não deve, sob nenhuma condição, carregar
#: framework de agente. Espelha a lista verificada manualmente na tarefa que criou este teste.
MODULES = (
    "app.modules.tickets.public",
    "app.modules.hitl.public",
    "app.modules.knowledge.public",
    "app.modules.audit.public",
    "app.modules.tenancy.public",
    "app.shared.auth",
)

_PROBE = """
import sys, importlib
importlib.import_module({module!r})
found = sorted({{k.split(".")[0] for k in sys.modules if k.split(".")[0] in {frameworks!r}}})
print(",".join(found))
"""


def puxados(module: str) -> list[str]:
    """Os pacotes de framework que entraram em `sys.modules` ao importar `module`, num processo novo."""
    script = _PROBE.format(module=module, frameworks=FRAMEWORKS)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    )
    saida = result.stdout.strip()
    return saida.split(",") if saida else []


def main() -> int:
    ok = True
    for module in MODULES:
        achados = puxados(module)
        if achados:
            ok = False
            print(f"  ❌ {module} puxa: {', '.join(achados)}")
        else:
            print(f"  ✅ {module} — limpo")

    if not ok:
        print(
            "\n❌ o núcleo limpo regrediu — um módulo que deveria ler a KB, gerenciar chamados,\n"
            "   decidir aprovação, checar papel ou ler a trilha sem framework de agente voltou a\n"
            "   carregar um. Reveja o import que introduziu a dependência (direto ou transitivo)."
        )
        return 1

    print(f"\n✅ os {len(MODULES)} módulos do núcleo limpo seguem sem framework de agente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
