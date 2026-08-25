"""A RESERVA DA DECISÃO — o que faz UM `requestState` valer por UMA escrita, e não por N.

O QUE ELA PRENDE É O NONCE, NÃO O HUMANO, e a diferença precisa estar escrita porque a versão
forte ("uma decisão humana, uma escrita") é sedutora e falsa. Um cliente pode chamar
`open_ticket` N vezes, receber N estados selados (N nonces), mostrar o formulário ao aprovador
UMA vez e responder as N chamadas com o mesmo conteúdo: saem N chamados e N eventos `approval`,
de uma decisão humana só. O protocolo não prova que existe um humano do outro lado — quem barra
de verdade é o PAPEL do token, e `tools_tickets` já diz isso no seu docstring. Esta reserva não
conserta essa parte e não tenta. O invariante que ela estabelece é o do título, e o que ela
fecha é o caminho barato: repetir o MESMO estado, que um retry banal de cliente LLM bastava para
disparar.

O `requestState` do protocolo (SEP-2322) é *verificável*, não é *de uso único*. Medido na fonte
instalada (`mcp/server/request_state.py:364-407`): o envelope carrega método, tool, digest dos
argumentos, principal e TTL — e nada por rodada. O `RequestStateBoundary` desela e segue; não há
nonce, não há consumo, e o próprio SDK diz o porquê no docstring da classe (ele protege a
INTEGRIDADE do estado; o que o estado significa é do servidor).

O resultado, medido contra o servidor antes deste módulo existir: o aprovador decide UMA vez, o
cliente repete `tools/call` com o mesmo `requestState` e as mesmas `input_responses`, e o
segundo e o terceiro chamados são criados — inclusive de sessão nova, dentro dos 600s de TTL. A
trilha grava dois `approval` + dois `write`, indistinguíveis de duas decisões humanas. Não é
escalação de privilégio (papel e principal seguram); é a quebra do invariante que a fase existe
para estabelecer, e faz a trilha da ADR-023 afirmar algo que não aconteceu. Um retry banal de
cliente LLM basta.

═══ O DESENHO: RESERVA ATÔMICA NUM ARQUIVO, NO SHARE QUE JÁ EXISTE ═══

O estado passa a carregar um NONCE por rodada — `open_ticket/v1:<nonce>` —, que o SDK sela junto
com o resto do envelope. O cliente não consegue forjar um nonce novo (o selo o recusaria) e não
consegue trocar o que veio; só consegue REPETIR. Então a segunda rodada começa RESERVANDO o
nonce, e reservar é a operação que só pode dar certo uma vez:

    os.open(caminho, O_CREAT | O_EXCL)

`O_EXCL` é create-if-absent atômico — o primeiro processo cria, todo o resto recebe
`FileExistsError`. Não é uma leitura seguida de uma escrita (que corre), é uma operação só.

POR QUE UM ARQUIVO, E NESTE LUGAR. O ambiente é hostil às duas soluções ingênuas: o app roda com
`minReplicas: 0` (desliga entre a pergunta e a resposta, então memória de processo não serve) e
pode haver mais de uma réplica (então um `set` local também não). O que sobrevive aos dois é
armazenamento compartilhado — e ele **já está montado**: `infra/containerapps.bicep` monta o
MESMO share do Azure Files nos dois apps, cada um na raiz do backend DA SUA IMAGEM (`/app/data`
no backend, `/srv/backend/data` aqui — as raízes diferem porque os Dockerfiles diferem), que é
onde `tickets.jsonl` vive. A reserva mora ao lado, em `data/decisoes/`. Nenhum recurso novo de
Azure, nenhuma dependência nova, nenhuma variável nova. Em SMB (que é como o share é montado —
`storageType: 'AzureFile'`), a criação com disposição *create-new* é atômica no servidor: é o
mesmo mecanismo de lock-file de sempre, não uma aposta no cliente.

═══ POR QUE NÃO A TRILHA DE AUDITORIA, QUE ERA A SUGESTÃO ═══

A ideia — gravar a decisão na trilha primeiro e recusar a escrita quando já existir evento de
escrita para aquela decisão — é atraente porque não inventa armazenamento. Foi medida e perde
por DUAS razões, e a segunda é fatal:

1. *Custo.* `audit.public` não tem consulta por id de evento: a única leitura é `read(scope)`, e
   `BlobTrail.read` **baixa o blob inteiro** e reparsa todas as linhas
   (`audit/internal/trail.py:201-213`). O escopo seria `approvals`, que é justamente o que cresce
   para sempre — uma linha por decisão e uma por escrita. Verificar idempotência custaria baixar
   a trilha inteira a cada tentativa de escrita.
2. *Corretude.* A trilha **não tem compare-and-set**. `BlobTrail.append` lê o topo e depois anexa,
   e o próprio arquivo documenta a consequência: "numa corrida, dois eventos podem ler o mesmo
   topo — e a VERIFICAÇÃO detecta" (`trail.py:226-228`). Detectar não é impedir. Duas réplicas
   repetindo a mesma decisão leriam as duas uma trilha sem o evento de escrita, e as duas
   escreveriam. Um livro de idempotência precisa de uma operação que falhe para o segundo; a
   trilha é um DETECTOR de adulteração, não um mutex.

A trilha continua sendo a camada de evidência — a recusa de replay **entra nela** (kind
`replay`), que é o que transforma a tentativa em rastro. Só não é ela quem decide.

═══ SEM SHARE MONTADO (DEV LOCAL) ═══

Não há ramo: o diretório é criado onde ele estiver. Em dev local `data/` é disco do processo, e
a reserva vale só para aquela máquina — a mesma limitação, e pelo mesmo motivo, que a trilha
declara quando não há `AZURE_STORAGE_ACCOUNT` ("isto não é auditoria; é o modo local"). O
comportamento do código é idêntico nos dois; o que muda é de quem é o disco.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import app as _app

logger = logging.getLogger(__name__)

#: A RAIZ DO BACKEND, não o pacote `app` — o mesmo alvo (e a mesma armadilha) documentados em
#: `app/modules/tickets/internal/tickets.py`: a raiz é onde o Azure Files é montado, e
#: `<raiz>/app/data` é disco efêmero. Ancorado no pacote (regra 9), nunca contando `parents[N]`
#: deste arquivo.
#:
#: NESTA IMAGEM A RAIZ É `/srv/backend`, não `/app` — o `apps/mcp/Dockerfile` põe o backend ali
#: (é irmão de `/srv/mcp` porque `pyproject.toml` o declara por path `../backend`), e `/app` nem
#: existe. `tests/decision_replay_test.py` compara este diretório com o de `tickets.jsonl` — os
#: dois são calculados separadamente e não podem divergir —, mas ser IRMÃO do errado também é
#: errado: quem compara com o `mountPath` do bicep, dentro da imagem, é
#: `tests/image_data_path_test.py`.
DIRETORIO = Path(_app.__file__).resolve().parent.parent / "data" / "decisoes"

#: O nonce é nosso (`secrets.token_urlsafe(24)` → 32 caracteres do alfabeto URL-safe) e vira NOME
#: DE ARQUIVO. A régua existe mesmo com o selo garantindo a origem: um nome de arquivo derivado de
#: dado que veio pelo fio é caminho até travessia de diretório, e "o selo garante" é exatamente o
#: tipo de premissa que a próxima refatoração quebra sem perceber.
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

#: Depois disto, uma reserva não protege mais nada: o TTL do envelope é de 600s, então um estado
#: com mais de uma hora já é recusado no fio como expirado, antes de chegar aqui. É o que permite
#: varrer o diretório em vez de deixá-lo crescer para sempre num share montado.
VALIDADE = 3600.0


class ConsumoIndisponivel(RuntimeError):
    """A reserva não pôde ser tomada — disco cheio, share fora do ar, permissão.

    Distinta de "já reservada" DE PROPÓSITO: uma é o replay que este módulo existe para barrar,
    a outra é o operador que precisa consertar alguma coisa. As duas impedem a escrita; só uma
    delas acusa o chamador de repetir.
    """


def novo() -> str:
    """O nonce de UMA rodada de decisão. Vai no `request_state`, e o SDK o sela."""
    return secrets.token_urlsafe(24)


def digest(nonce: str) -> str:
    """Como a decisão é NOMEADA na trilha — o nonce nunca em claro.

    Ele não é um segredo por si (sozinho não abre nada: só vale dentro do envelope selado), mas
    a trilha é imutável e pública para quem audita, e publicar em claro o identificador de um
    fluxo de autorização é hábito ruim que custa caro no dia em que ele passar a valer sozinho.
    """
    return hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:16]


def consumir(nonce: str) -> bool:
    """Reserva o nonce. `True` se ESTA chamada o tomou; `False` se alguém já o tinha tomado.

    `False` é o replay. Não há terceiro valor: falha de infraestrutura levanta
    `ConsumoIndisponivel`, porque "não consegui saber" nunca pode ser lido como "pode escrever".
    """
    if not _NONCE.match(nonce or ""):
        # Não deveria acontecer (o nonce é nosso e vem selado), e por isso mesmo é fail-closed:
        # um estado que não carrega nonce reconhecível não autoriza escrita nenhuma.
        logger.error("nonce de decisão fora do formato — a escrita foi recusada")
        return False

    caminho = DIRETORIO / f"{nonce}.json"
    try:
        DIRETORIO.mkdir(parents=True, exist_ok=True)
        fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    except OSError as exc:
        raise ConsumoIndisponivel(str(exc)) from exc

    # O CONTEÚDO NÃO IMPORTA — quem responde "esta decisão já foi usada?" é a EXISTÊNCIA do
    # arquivo, e ela já foi decidida acima. O carimbo de tempo entra só para a varredura poder
    # distinguir reserva viva de reserva vencida sem depender do `mtime` do sistema de arquivos.
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now(UTC).isoformat(timespec="seconds")}))
    _varrer()
    return True


def _varrer() -> None:
    """Apaga reservas vencidas. Best-effort: falhar aqui não pode derrubar uma escrita legítima.

    Sem isto, o diretório cresce para sempre num share montado — um arquivo por decisão aprovada,
    para sempre. Uma reserva vencida não protege nada (o envelope que a citaria já expirou), então
    apagá-la não afrouxa o invariante.
    """
    limite = time.time() - VALIDADE
    with contextlib.suppress(OSError):
        for arquivo in DIRETORIO.iterdir():
            with contextlib.suppress(OSError):
                if arquivo.suffix == ".json" and arquivo.stat().st_mtime < limite:
                    arquivo.unlink()
