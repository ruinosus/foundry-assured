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
import tomllib
from pathlib import Path

import app as _app

BACKEND = Path(_app.__file__).resolve().parent.parent
IMPORTLINTER_TOML = BACKEND / "importlinter.toml"

#: Nome do contrato C4b em `importlinter.toml`, cujos `source_modules` devem espelhar `MODULES`
#: abaixo (exceto `hitl` — ver `checar_paridade_com_toml`).
CONTRATO_C4B = "nucleo limpo: sem framework de agente"

#: `hitl` existe só aqui, nunca em `source_modules` do contrato estático: o contrato C4b prova o
#: grafo ESTÁTICO, cego a quando um import roda, e `hitl/public.py` mantém de propósito um import
#: PREGUIÇOSO que alcança LangChain só sob chamada — a mesma aresta, no grafo estático, de uma
#: regressão real (import a frio). Ver o comentário do contrato C4b em `importlinter.toml`.
EXCECAO_NOMEADA = "app.modules.hitl.public"

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


def checar_paridade_com_toml() -> str | None:
    """Confere que `MODULES` e os `source_modules` do contrato C4b são o mesmo conjunto, com
    `hitl` como a única exceção nomeada. Nada amarrava as duas listas antes deste teste: um
    módulo novo adicionado só a uma recebia metade da cobertura, sem erro — só menos gate.

    Retorna uma mensagem de erro (com o módulo e o lado onde ele diverge) ou `None` se bater.
    """
    dados = tomllib.loads(IMPORTLINTER_TOML.read_text())
    contratos = dados["tool"]["importlinter"]["contracts"]
    contrato = next((c for c in contratos if c["name"] == CONTRATO_C4B), None)
    if contrato is None:
        return f"contrato {CONTRATO_C4B!r} não encontrado em {IMPORTLINTER_TOML}"

    do_toml = set(contrato["source_modules"])
    do_teste = set(MODULES) - {EXCECAO_NOMEADA}

    so_no_teste = do_teste - do_toml
    so_no_toml = do_toml - do_teste
    if so_no_teste or so_no_toml:
        partes = []
        if so_no_teste:
            partes.append(f"só em MODULES (nucleo_limpo_test.py): {sorted(so_no_teste)}")
        if so_no_toml:
            partes.append(f"só em source_modules (importlinter.toml, contrato C4b): {sorted(so_no_toml)}")
        return "MODULES e o contrato C4b divergem — " + "; ".join(partes)

    return None

_PROBE = """
import sys, importlib
importlib.import_module({module!r})
found = sorted({{k.split(".")[0] for k in sys.modules if k.split(".")[0] in {frameworks!r}}})
print(",".join(found))
"""


def puxados(module: str) -> list[str]:
    """Os pacotes de framework que entraram em `sys.modules` ao importar `module`, num processo novo.

    Levanta `RuntimeError` (com o `stderr` do subprocesso) se o próprio import falhar — para o
    gate nomear o módulo e mostrar a causa, em vez de morrer com um `CalledProcessError` cru que
    o CI mostraria como traceback do harness, não como "módulo X não importa".
    """
    script = _PROBE.format(module=module, frameworks=FRAMEWORKS)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{module} não importa:\n{result.stderr}")
    saida = result.stdout.strip()
    return saida.split(",") if saida else []


def main() -> int:
    ok = True

    divergencia = checar_paridade_com_toml()
    if divergencia:
        print(f"  ❌ {divergencia}")
        return 1

    for module in MODULES:
        try:
            achados = puxados(module)
        except RuntimeError as exc:
            print(f"  ❌ {exc}")
            return 1
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
