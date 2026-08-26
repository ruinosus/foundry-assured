"""O estado por usuário entre chamadas — o que ele guarda, por que não cabe no fio, e o TTL.

═══ O CASO DE USO, PORQUE SESSÃO SEM CASO DE USO É INFRAESTRUTURA PARA NADA ═══

Guarda **as citações da última busca do chamador**, e serve uma coisa só: o app de evidências
(`mcp_app/app_evidencias.py`) renderiza aquela tabela sem refazer a busca.

Três perguntas decidem se isso merece estado no servidor, e as três têm resposta medida:

**1. Por que não cabe no fio?** Este servidor JÁ tem estado entre chamadas, e ele viaja selado
(SEP-2322, `mcp_app/request_state.py`) — foi a resposta certa para a decisão humana e continua
sendo. Não serve aqui: o envelope do `RequestStateBoundary` é amarrado ao **nome da tool** e ao
**digest dos argumentos**, então um estado emitido por `search_docs` é RECUSADO no fio quando
devolvido a `show_evidence`. Não é preferência de desenho — é o mecanismo se recusando, e o gate
mede a recusa. O fio costura duas rodadas da MESMA chamada; isto é outra chamada.

**2. Por que não recalcular?** Porque a resposta seria diferente, e a diferença é justamente o
que a tabela existe para não ter. Refazer a busca dentro de `show_evidence` consultaria o índice
de novo: outra ordem, outro `top`, e possivelmente outros documentos. A tabela mostraria fontes
que não são as que sustentam a resposta que a pessoa está lendo — uma tabela de evidências que
discorda da evidência é pior que nenhuma tabela.

**3. O que se perde quando o estado some?** Uma tabela vazia com o texto "nenhuma busca nesta
sessão". Nada é negado, nada é concedido, nada é gravado errado. Esta é a propriedade que torna
o item seguro: **a sessão nunca é uma permissão** — os gates de papel, de tenant e de ACL rodam
na mesma chamada, sobre o mesmo chamador, exatamente como antes.

═══ O QUE NÃO ENTRA NA SESSÃO, E POR QUÊ ═══

- **A pergunta do usuário não entra.** Só o que ela devolveu. A `query` é conteúdo escrito por
  uma pessoa e não é preciso para renderizar a tabela — guardá-la seria dado a mais em repouso
  sem consumidor, que é como um cache vira um repositório sem ninguém decidir isso.
- **O conteúdo dos documentos não entra.** Só `index`, `source` e `url` — os MESMOS três campos
  que a tool acabou de devolver ao mesmo chamador, e os mesmos que o selo de assurance publica.
  Nada aqui é revelado que não tenha sido revelado.
- **Nada disso vale como autorização depois.** Abrir um documento continua passando por
  `document://`, que reautoriza a cada leitura — o direito não se herda de uma citação, que é a
  regra que `resources_knowledge` escreve por extenso.

═══ A LOJA, E O TTL QUE O FASTMCP NÃO IMPÕE ═══

`Session._save_raw` chama `put` **sem TTL** — a fonte diz, com todas as letras, que a retenção é
inteiramente da loja. Uma `RedisStore` crua, portanto, guardaria as citações de cada usuário
**para sempre**. `TTLClampWrapper(missing_ttl=…)` é o que o próprio pacote oferece para isso, e
é o que transforma "cache de sessão" em algo que de fato expira: medido, a chave gravada volta
com `TTL=3590`.

Sem `MCP_REDIS_URL` a loja é a `MemoryStore()` de processo — o default do FastMCP. Não é um erro:
é o modo de repouso, e com `minReplicas: 0` significa que a tabela some quando a réplica dorme.
A degradação é declarada aqui e provada no gate, não descoberta em produção.

═══ E COM `MCP_REDIS_URL` APONTANDO PARA UM REDIS QUE NÃO RESPONDE ═══

Aqui estava o defeito, e ele era do tamanho do servidor inteiro. A loja NÃO é lida só por
`guardar_evidencia`/`evidencia_guardada` — que engolem falha de propósito, ver abaixo. O FastMCP
a lê em TODA requisição, por dentro: `transforms/visibility.py:316 get_visibility_rules` chama
`Context.get_state`, que vai ao `_state_store`. Medido, com o Redis fora do ar e uma `RedisStore`
crua: `tools/list`, `prompts/list`, `resources/list`, `resources/read` e `tools/call` voltam
todos `MCPError: Internal server error`, com `redis.exceptions.ConnectionError` no traceback.
As cinco superfícies de leitura morriam por causa de um cache — inclusive a busca síncrona, que
não precisa de Redis para nada.

O conserto é o `FallbackWrapper` do próprio pacote: falha do Redis cai para a `MemoryStore()` de
processo, que é EXATAMENTE a loja do modo sem Redis. Isto é o que faz a degradação por
indisponibilidade ser a MESMA degradação já declarada por ausência de configuração — nenhum
comportamento novo para ninguém entender, e o Basic C0 (que não tem réplica, por escolha de SKU)
pode entrar em manutenção sem levar a leitura junto.

`write_to_fallback=True` de propósito: sem ele a escrita ainda levantaria, e a sessão de quem
buscou durante a queda ficaria sem destino nenhum. Com ele, ela vive na memória da réplica —
de novo, o modo de repouso. A inconsistência que o wrapper avisa (o que foi para a memória não
volta ao Redis quando ele volta) é uma tabela de evidências que some, que é o que a pergunta 3
acima diz que é aceitável perder.
"""

from __future__ import annotations

import logging
from typing import Any

from app.shared.settings import settings

logger = logging.getLogger(__name__)

#: A COLEÇÃO NÃO É NOSSA, e havia aqui uma constante afirmando que era. `default_collection=` da
#: loja é inerte neste caminho: o FastMCP embrulha o que passamos num
#: `PydanticAdapter(default_collection="fastmcp_state")` (`server.py:499`), e o adapter passa a
#: coleção EXPLÍCITA em toda chamada — o default da loja nunca é consultado. Medido, a chave real
#: no Redis é `fastmcp_state::session:<sha256(principal)>:_user`.
#:
#: O keyspace separado que a constante prometia, portanto, já existe — sob o nome do FastMCP, não
#: sob o nosso. E a justificativa que ela carregava era errada de qualquer jeito: `FLUSHDB` apaga
#: o banco inteiro, prefixo nenhum protege de `FLUSHDB`. Fica o fato medido, no lugar da promessa.

#: Uma hora. É a vida útil de "o que eu acabei de buscar" — passado isso, a pessoa buscou de
#: novo ou já foi embora. Curto de propósito: cada hora a mais é uma hora a mais de nomes de
#: documento em repouso, sem nenhum ganho para quem está usando.
TTL_SEGUNDOS = 3600

#: Segundos que uma operação da loja pode levar antes de o fallback assumir. UM segundo é ~20x o
#: que um Redis na mesma região leva, e a loja está no caminho de TODA requisição — esperar mais
#: que isso por um CACHE é transformar uma degradação em lentidão para quem só quis buscar.
#: Medido: sem teto, o `redis-py` gasta os retries dele e cada requisição custava ~4s.
TIMEOUT_LOJA_SEGUNDOS = 1.0

#: Quantas citações a sessão guarda. A busca já devolve um punhado; o teto existe para que uma
#: mudança de `top` lá não vire, sem ninguém decidir, um registro grande por usuário aqui.
MAX_CITACOES = 20

#: A chave dentro do estado do usuário. Uma constante porque quem escreve (`tools_knowledge`) e
#: quem lê (`app_evidencias`) são módulos diferentes — a string literal nos dois lados é a
#: divergência silenciosa de sempre.
CHAVE_EVIDENCIAS = "ultima_evidencia"


def loja():
    """A loja de estado para `FastMCP(session_state_store=...)`, ou `None` para o default.

    `None` deixa o FastMCP construir a `MemoryStore()` dele — devolver uma nossa seria criar um
    segundo default para a mesma coisa.
    """
    url = settings.mcp_redis_url.strip()
    if not url:
        logger.info(
            "sessão por usuário em memória de processo (sem MCP_REDIS_URL) — com minReplicas: 0 "
            "ela some quando a réplica dorme. A tabela de evidências degrada para vazia."
        )
        return None

    from key_value.aio.stores.memory import MemoryStore
    from key_value.aio.stores.redis import RedisStore
    from key_value.aio.wrappers.fallback import FallbackWrapper
    from key_value.aio.wrappers.timeout import TimeoutWrapper
    from key_value.aio.wrappers.ttl_clamp import TTLClampWrapper
    from redis.exceptions import RedisError

    # O TTL POR FORA DOS DOIS, e não só por cima do Redis: `missing_ttl` é o que transforma o
    # `put` sem ttl do FastMCP em algo que expira, e a memória de processo precisa dele tanto
    # quanto o Redis — durante uma queda longa, é ela que guarda os nomes de documento.
    # `min`/`max` existem para aparar um ttl explícito, que aqui nunca acontece.
    return TTLClampWrapper(
        key_value=FallbackWrapper(
            # O TIMEOUT NÃO É PARANOIA, É NÚMERO MEDIDO. Sem ele, o `redis-py` gasta os próprios
            # retries com backoff antes de desistir: com o Redis fora do ar, CADA requisição do
            # servidor levava ~4s para cair no fallback — e a loja está no caminho de toda
            # requisição (é isso que o docstring explica). `TIMEOUT_LOJA_SEGUNDOS` é o teto, e
            # `asyncio.TimeoutError` é `TimeoutError`, subclasse de `OSError`: ele cai no
            # `fallback_on` abaixo sem precisar ser listado à parte.
            primary_key_value=TimeoutWrapper(
                key_value=RedisStore(url=url), timeout=TIMEOUT_LOJA_SEGUNDOS
            ),
            fallback_key_value=MemoryStore(),
            # O ALVO É A INDISPONIBILIDADE, NÃO TODO ERRO. `redis.exceptions.RedisError` cobre
            # conexão recusada, timeout e o servidor respondendo erro; `OSError` cobre o socket
            # antes de o cliente ter algo a dizer. O default do wrapper é `(Exception,)` — largo
            # demais: um defeito de serialização nosso viraria "leitura vazia" em silêncio, com
            # o Redis de pé.
            fallback_on=(RedisError, OSError),
            # Ver o docstring: sem isto a ESCRITA continuaria levantando durante a queda.
            write_to_fallback=True,
        ),
        min_ttl=60,
        max_ttl=TTL_SEGUNDOS,
        missing_ttl=TTL_SEGUNDOS,
    )


def evidencia_para_guardar(domain: str, fontes: list[dict[str, Any]]) -> dict[str, Any]:
    """O registro que vai para a sessão — construído aqui para haver UMA forma.

    Copia os três campos que a tool já publicou, e nada mais. Ver a seção "o que não entra" no
    docstring: sem a pergunta, sem o conteúdo, com teto.
    """
    return {
        "domain": domain,
        "sources": [
            {"index": f.get("index"), "source": f.get("source"), "url": f.get("url")}
            for f in fontes[:MAX_CITACOES]
            if isinstance(f, dict)
        ],
    }


async def guardar_evidencia(domain: str, fontes: list[dict[str, Any]]) -> None:
    """Grava as citações da busca na sessão do chamador. Silencioso quando não há sessão.

    NUNCA LEVANTA, e isto é decisão de desenho, não descuido. Esta função roda DEPOIS de a busca
    ter dado certo, dentro da mesma chamada: um Redis indisponível não pode transformar uma busca
    bem-sucedida em erro para quem perguntou. O que se perde é a tabela de evidências, que é
    exatamente o que a pergunta 3 do docstring diz que é aceitável perder.

    Sem chamador autenticado, `OptionalCurrentSession` devolve `None` e nada é gravado — a
    sessão é keyed pelo principal, e sem principal não há isolamento nenhum para guardar.
    """
    from fastmcp.server.sessions import OptionalCurrentSession

    try:
        async with OptionalCurrentSession() as sessao:
            if sessao is None:
                return
            await sessao.set(CHAVE_EVIDENCIAS, evidencia_para_guardar(domain, fontes))
    # Larga de propósito: o docstring explica por quê — a busca não pode falhar por causa
    # de um cache, e não há exceção específica que a loja garanta levantar.
    except Exception:
        logger.warning("não foi possível guardar a evidência na sessão", exc_info=True)


async def evidencia_guardada() -> dict[str, Any] | None:
    """As citações da última busca do chamador, ou `None` quando não há.

    `None` cobre os três casos que se parecem de fora e não precisam ser distinguidos para quem
    lê: sem sessão (chamador não autenticado), sem busca ainda, e loja indisponível. A tabela
    diz a mesma coisa nos três — "nenhuma busca nesta sessão" —, e distinguir contaria ao
    chamador coisas sobre a infraestrutura que ele não pediu (o mesmo raciocínio do
    `mask_error_details`).
    """
    from fastmcp.server.sessions import OptionalCurrentSession

    try:
        async with OptionalCurrentSession() as sessao:
            if sessao is None:
                return None
            guardado = await sessao.get(CHAVE_EVIDENCIAS)
    # Larga pelo mesmo motivo da irmã acima: a tabela degrada para vazia, nada mais.
    except Exception:
        logger.warning("não foi possível ler a evidência da sessão", exc_info=True)
        return None
    return guardado if isinstance(guardado, dict) else None
