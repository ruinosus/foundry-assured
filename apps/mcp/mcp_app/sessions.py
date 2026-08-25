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
"""

from __future__ import annotations

import logging
from typing import Any

from app.shared.settings import settings

logger = logging.getLogger(__name__)

#: A coleção (prefixo) das chaves de sessão dentro do Redis. Nomeada porque a mesma instância
#: serve o Docket, que tem o prefixo dele: sem coleção própria, as duas famílias de chave
#: dividiriam o keyspace e um `FLUSHDB` de manutenção de uma levaria a outra junto.
COLECAO = "mcp_session_state"

#: Uma hora. É a vida útil de "o que eu acabei de buscar" — passado isso, a pessoa buscou de
#: novo ou já foi embora. Curto de propósito: cada hora a mais é uma hora a mais de nomes de
#: documento em repouso, sem nenhum ganho para quem está usando.
TTL_SEGUNDOS = 3600

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

    from key_value.aio.stores.redis import RedisStore
    from key_value.aio.wrappers.ttl_clamp import TTLClampWrapper

    # `missing_ttl` é o parâmetro que faz o trabalho: ele é aplicado justamente ao `put` que
    # chega SEM ttl, que é o único jeito como o FastMCP escreve sessão. `min`/`max` existem para
    # aparar um ttl explícito, que aqui nunca acontece.
    return TTLClampWrapper(
        key_value=RedisStore(url=url, default_collection=COLECAO),
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
