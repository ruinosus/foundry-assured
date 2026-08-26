"""O CAMINHO DE DADOS QUE A IMAGEM RESOLVE É O `mountPath` QUE O BICEP DECLARA.

    docker build -f apps/mcp/Dockerfile -t foundry-assured-mcp:ci .
    docker run --rm \
      -v "$PWD/infra:/infra:ro" \
      -v "$PWD/apps/mcp/tests/image_data_path_test.py:/gate/image_data_path_test.py:ro" \
      -e MCP_BICEP=/infra/containerapps.bicep -e PYTHONPATH=/gate \
      foundry-assured-mcp:ci python -m image_data_path_test

ESTE GATE SÓ PROVA ALGO DENTRO DA IMAGEM, e é por isso que ele é invocado por `docker run` em
vez de entrar na bateria de `scripts/gates.py`. A raiz do backend é uma propriedade do
Dockerfile, não do repositório: na árvore de trabalho ela é `apps/backend`, o que não é o que a
Azure monta em lugar nenhum. Rodado no host, ele fica vermelho — corretamente, porque ali a
pergunta não tem resposta. Mora no job `mcp-image` do CI, logo depois do build, pelo mesmo
motivo que o build mora lá (`scripts/gates.py:42`: `DEFAULT_JOBS` é offline e determinístico, e
`docker` não é nenhum dos dois).

═══ O DEFEITO QUE ELE EXISTE PARA PEGAR, MEDIDO ═══

O `mountPath` do container do MCP era `/app/data` — copiado do backend. Medido na imagem real:

    docker run --rm foundry-assured-mcp:ci python -c "import app; print(app.__file__)"
    → /srv/backend/app/__init__.py

isto é, `Path(app.__file__).parent.parent` = `/srv/backend`, e **`/app` não existe** nesta
imagem. O `apps/mcp/Dockerfile` põe o backend em `/srv/backend` porque `apps/mcp/pyproject.toml`
o declara por path (`../backend`), o que obriga os dois a serem irmãos.

Duas consequências, as duas silenciosas:

    tickets.jsonl    o chamado aberto por MCP ia para o disco efêmero da réplica. A escrita
                     "funcionava", o cliente recebia o id, e a página `/tickets` nunca o via.
    data/decisoes/   a reserva de nonce (Fase 3) morria no scale-to-zero, e o mesmo
                     `requestState` selado escrevia de novo dentro do TTL de 600s — o invariante
                     "um `requestState`, uma escrita" evaporava no cenário que ele cobre.

POR QUE `decision_replay_test` NÃO PEGOU: o item 6 dele assere que os dois caminhos são
**irmãos** (`real_reservas.parent == real_chamados.parent`), e isso é verdade também quando os
dois estão no disco errado. Irmandade não é endereço. Este gate compara com a fonte que declara
o endereço — o bicep — em vez de comparar um caminho com o outro.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import app as _app
from app.modules.tickets.internal.tickets import _STORE
from mcp_app.decision_claim import DIRETORIO as _RESERVAS

#: O recurso do bicep cujo `volumeMounts` interessa. O arquivo declara o volume `data` DUAS
#: vezes (backend e MCP) com caminhos diferentes de propósito — um `re.search` no arquivo
#: inteiro devolveria o do backend e daria verde por acidente.
_RECURSO = "mcpApp"
_VOLUME = "data"


def mount_do_bicep(texto: str) -> str | None:
    """O `mountPath` do volume `data` DENTRO do recurso `mcpApp`, ou None.

    O recorte é do `resource mcpApp` até o próximo `resource ` de primeiro nível (ou o fim do
    arquivo) — o suficiente para não alcançar o container do backend, e sem parser de bicep.
    """
    inicio = texto.find(f"resource {_RECURSO} ")
    if inicio < 0:
        return None
    fim = texto.find("\nresource ", inicio + 1)
    bloco = texto[inicio : fim if fim > 0 else len(texto)]
    m = re.search(rf"volumeName:\s*'{_VOLUME}'\s*,\s*mountPath:\s*'([^']+)'", bloco)
    return m.group(1) if m else None


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    bicep = Path(os.environ.get("MCP_BICEP", "/infra/containerapps.bicep"))
    check(f"o bicep está montado em {bicep}", bicep.is_file())
    if not bicep.is_file():
        print("\n❌ sem o bicep não há com o que comparar — monte `infra/` no container.")
        return 1

    mount = mount_do_bicep(bicep.read_text(encoding="utf-8"))
    check(f"o bicep declara o mount do volume '{_VOLUME}' em `{_RECURSO}`", mount is not None)
    if not mount:
        print(f"\n❌ mount não encontrado dentro de `resource {_RECURSO}` — o recurso mudou de nome?")
        return 1

    raiz = Path(_app.__file__).resolve().parent.parent
    print(f"     app.__file__       : {_app.__file__}")
    print(f"     raiz do backend    : {raiz}")
    print(f"     mountPath do bicep : {mount}")
    print(f"     tickets.jsonl      : {_STORE}")
    print(f"     reservas de decisão: {_RESERVAS}")

    # A RAIZ, e não só os arquivos: é ela que o código deriva de `app.__file__`, e é o que o
    # bicep tem que espelhar. Comparar só os arquivos deixaria passar um mount que cobre o
    # `tickets.jsonl` sem cobrir o `data/` inteiro.
    esperado = Path(mount)
    check(
        f"o mount aponta para `<raiz do backend>/data` desta imagem ({raiz / 'data'})",
        esperado == raiz / "data",
    )
    check(f"`tickets.jsonl` cai dentro do mount ({_STORE.parent})", _STORE.parent == esperado)
    check(f"as reservas de decisão caem dentro do mount ({_RESERVAS.parent})",
          _RESERVAS.parent == esperado)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print("   O `mountPath` do bicep e o caminho que ESTA imagem resolve discordam. Nada")
        print("   falha em runtime: o diretório passa a existir no disco efêmero da réplica, a")
        print("   escrita funciona, e o chamado some no scale-to-zero — junto com a reserva que")
        print("   impede um `requestState` de abrir um segundo chamado.")
        return 1
    print("\n✅ o caminho de dados desta imagem é exatamente o que o bicep monta nela.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
