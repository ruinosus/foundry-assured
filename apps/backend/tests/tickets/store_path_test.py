"""O arquivo de chamados cai DENTRO do volume montado — comparado com o bicep, não presumido.

    uv run python -m tests.tickets.store_path_test

POR QUE ESTE GATE EXISTE, e por que o de anchors não bastava. `filesystem_anchors_test` verifica
duas coisas: que nenhum caminho é contado por `parents[N]` a partir do próprio arquivo, e que
caminhos estaticamente conhecidos apontam para algo que existe. O caminho dos chamados passava nas
duas — e mesmo assim escrevia no lugar errado.

Ele já errou DUAS vezes, das duas por contagem:

    parents[3] do arquivo   → app/modules/data/   (quando a ADR-017 moveu o arquivo dois níveis)
    Path(app).parent/data   → /app/app/data/      (a "correção", que ancorou no pacote errado)

O mount declarado em `infra/containerapps.bicep` é `/app/data`. No container, `WORKDIR /app` +
`COPY app ./app` põem o pacote em `/app/app/`, então ancorar no PACOTE erra por um nível — e erra
em silêncio, porque o diretório passa a existir e a escrita funciona. O sintoma só aparece no
restart, quando os chamados somem.

Por isso este teste lê o BICEP: a única forma de não repetir o erro é comparar com a fonte que
declara o mount, em vez de reafirmar o que alguém achou que ela dizia.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import app as _app

from app.modules.tickets.internal.tickets import _STORE

#: A raiz do repositório, ancorada no pacote `app` (regra 9): app → apps/backend → apps → raiz.
_REPO = Path(_app.__file__).resolve().parent.parent.parent.parent
_BICEP = _REPO / "infra" / "containerapps.bicep"

#: O volume que guarda os chamados, como o bicep o nomeia.
_VOLUME = "data"


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    check("o bicep de container apps existe", _BICEP.is_file())
    if not _BICEP.is_file():
        print("\n❌ sem o bicep não há com o que comparar.")
        return 1

    texto = _BICEP.read_text(encoding="utf-8")
    m = re.search(rf"volumeName:\s*'{_VOLUME}'\s*,\s*mountPath:\s*'([^']+)'", texto)
    check(f"o bicep declara o mount do volume '{_VOLUME}'", m is not None)
    if not m:
        print("\n❌ mount não encontrado — o nome do volume mudou no bicep?")
        return 1

    mount = m.group(1)
    print(f"     mount declarado: {mount}")

    # No container o backend roda de /app, e é lá que o mount aparece. Localmente a raiz do
    # backend é apps/backend — o teste compara a POSIÇÃO RELATIVA, que é o que viaja.
    raiz_backend = Path(_app.__file__).resolve().parent.parent
    relativo = _STORE.resolve().relative_to(raiz_backend)
    esperado = Path(mount.lstrip("/")).relative_to("app") / "tickets.jsonl"

    print(f"     caminho relativo à raiz do backend: {relativo}")
    print(f"     esperado pelo mount:                {esperado}")
    check("o arquivo de chamados cai dentro do volume montado", relativo == esperado)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print("   Um chamado fora do volume some no restart do container — sem erro nenhum,")
        print("   porque a escrita funciona e o diretório passa a existir.")
        return 1
    print("\n✅ os chamados são gravados dentro do volume que o bicep monta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
