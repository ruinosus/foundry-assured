"""Os contratos de privacidade do import-linter cobrem TODOS os módulos, sem buraco.

Este gate existe porque o outro gate mentia. Cada contrato `<x> internals are private` lista
à mão, em `source_modules`, quais módulos são proibidos de tocar o `internal` de `<x>` — e cada
um nasceu copiando a lista da época. Nenhum foi atualizado quando um módulo novo entrou.

O resultado, medido em 2026-08: `Contracts: 22 kept, 0 broken` com

  - `builder` e `pricing` SEM contrato nenhum — internals inteiramente livres;
  - os 18 contratos existentes ignorando ~10 módulos cada.

Concretamente: `app.modules.oncall` importando `app.modules.knowledge.internal` passava no
gate. Não passava por decisão nenhuma — passava porque `oncall` não estava na lista de
`knowledge`, e nada acusava a ausência. É a mesma família de falha do `TECHDOCS_*` vs
`COCKPIT_*`: o ambiente fica verde e ninguém descobre que ele parou de verificar.

Um buraco de cobertura não pode se anunciar sozinho — por definição, ele é a AUSÊNCIA de uma
linha. Só um teste que compara a configuração com a realidade do disco vê isso.

A lista canônica de `source_modules` de `<x>` é: todo módulo em `app/modules/` menos `<x>`,
mais a composition root (`app.main`, `app.registry`) e `app.shared` — porque a regra da ADR-017
é que ninguém, nem o compositor, alcança o `internal` de outro módulo.

    uv run python -m tests.architecture.importlinter_coverage_test
"""

from __future__ import annotations

import pathlib
import sys
import tomllib

import app as _app

# Ancorado no pacote `app`, nunca contado por `parents[N]` a partir deste arquivo (regra 9).
BACKEND = pathlib.Path(_app.__file__).resolve().parent.parent
MODULES_DIR = BACKEND / "app" / "modules"
CONFIG = BACKEND / "importlinter.toml"

#: Fontes que todo contrato de privacidade carrega além dos outros módulos.
COMPOSITION = ("app.main", "app.registry", "app.shared")

SUFIXO = " internals are private"


def modules() -> list[str]:
    return sorted(
        p.name
        for p in MODULES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(("_", "."))
    )


def problems() -> list[str]:
    config = tomllib.loads(CONFIG.read_text())
    contracts = config["tool"]["importlinter"]["contracts"]
    privacy = {
        c["name"][: -len(SUFIXO)]: c for c in contracts if c["name"].endswith(SUFIXO)
    }
    found: list[str] = []

    for module in modules():
        contract = privacy.get(module)
        if contract is None:
            found.append(f"{module}: sem contrato de privacidade — o internal está livre")
            continue

        expected = {f"app.modules.{m}" for m in modules() if m != module}
        expected |= set(COMPOSITION)
        missing = expected - set(contract["source_modules"])
        if missing:
            names = ", ".join(sorted(m.split(".")[-1] for m in missing))
            found.append(f"{module}: o contrato não vigia {names}")

        forbidden = contract.get("forbidden_modules", [])
        if forbidden != [f"app.modules.{module}.internal"]:
            found.append(f"{module}: forbidden_modules deveria ser o próprio internal, é {forbidden}")

        # Sem isto, toda cadeia legítima composition -> public -> internal vira violação.
        if not contract.get("allow_indirect_imports"):
            found.append(f"{module}: falta allow_indirect_imports = true")

    extra = sorted(set(privacy) - set(modules()))
    found += [f"{name}: contrato para módulo que não existe mais" for name in extra]
    return found


def main() -> int:
    found = problems()
    if found:
        print("❌ os contratos do import-linter têm buraco de cobertura:\n")
        for problem in found:
            print(f"  ✗ {problem}")
        print(
            "\n   Um módulo fora do `source_modules` de um contrato NÃO é vigiado por ele, e"
            "\n   o import-linter reporta `kept` mesmo assim. Complete a lista em"
            "\n   importlinter.toml — a skill `novo-modulo` explica o formato."
        )
        return 1

    total = len(modules())
    print(f"✅ os {total} módulos têm contrato de privacidade, e cada um vigia os outros {total - 1}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
