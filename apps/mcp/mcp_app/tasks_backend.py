"""As background tasks (SEP-2663) — o que vira task, o que não vira, e o que elas exigem antes.

═══ O CRITÉRIO, ESCRITO ANTES DA LISTA ═══

Uma tool vira task quando **o tempo dela não é nosso**: quando o custo dominante é uma chamada a
um serviço remoto cuja latência não controlamos e não podemos limitar sem mentir sobre o
resultado. Não vira task por ser importante, e não vira task porque dá.

O critério é sobre a FORMA do trabalho, não sobre o relógio de hoje, e isso é de propósito. Uma
tool medida hoje em 300ms contra um corpus de treze runbooks não deixa de ser uma chamada remota
não limitada — ela só ainda não encontrou o índice que a torna lenta. Esperar o sintoma para
decidir significa decidir no dia em que o cliente já está esperando.

Aplicado às duas tools de hoje:

- **`search_docs` vira task.** O corpo dela é uma chamada ao Azure AI Search pelo `retrieve` do
  backend, sob OBO, contra um índice cujo tamanho é do cliente. Nada neste repositório governa
  esse número: um corpus maior, um `top` maior ou uma reformulação semântica o movem sem uma
  linha de diff aqui.
- **`open_ticket` NÃO vira task**, por duas razões independentes. O trabalho dela é um append
  local, em milissegundos — o que demora é o HUMANO, e o humano já tem o mecanismo próprio do
  protocolo (a suspensão do SEP-2322, `mcp_app/tools_tickets.py`). Compor as duas suspensões
  colocaria DOIS relógios sobre a mesma espera, o TTL do `requestState` e o TTL da task, e os
  dois desfechos de um vencer antes do outro são inaceitáveis na única superfície de escrita do
  produto: uma decisão aprovada que não escreve, ou uma escrita cujo `requestState` já não vale.

`task=True` é `mode="optional"`: quem decide, chamada a chamada, é o CLIENTE. Um cliente que não
pede task recebe exatamente a resposta síncrona de sempre. É por isso que este item entra sem
período de convivência e sem flag de produto — ele não tira nada de ninguém.

═══ AS DUAS VARIÁVEIS, E POR QUE NENHUMA É OPCIONAL ═══

1. **`MCP_REDIS_URL`** — o backend do Docket. O default do pacote é `memory://`, descrito na
   própria fonte como *"In-memory backend (single process only)"*, e este app roda com
   `minReplicas: 0`: ele DESLIGA por ociosidade. Medido, com `memory://`, uma task submetida num
   processo e consultada de outro responde `Task <id> not found` — **depois** de o servidor ter
   prometido `ttl_ms=900000` e `poll_interval_ms=5000` ao cliente. É o pior formato de falha
   possível: o servidor promete quinze minutos de vida e o cliente vai bater na porta 180 vezes
   contra um id que não existe mais.

2. **`FASTMCP_TASKS_ENCRYPTION_KEY`** — e esta é a que decide se o item podia entrar. Ela paga
   DUAS coisas, e a segunda é a que importa mais.

   *A primeira é segredo em repouso.* O snapshot de contexto que o pacote grava no backend
   **carrega o access token do chamador e todos os headers HTTP dele** — é o que faz o worker
   rodar a busca sob a identidade certa, com o trim de ACL do chamador e o ator certo na trilha.
   Sem a chave o pacote grava esse snapshot em **JSON claro**; medido, lendo a chave crua do
   Redis: `{"access_token_json": "{\\"token\\": \\"eyJ0eXAi…\\"}", "http_headers":
   {"authorization": "Bearer eyJ0eXAi…"}}`. Token de usuário em claro num cache é o achado que a
   NORDOR-122 descreve por extenso, e nenhuma conveniência o compra.

   *A segunda é a identidade falhar FECHADA.* `restore_task_snapshot` documenta, na fonte, que
   sem chave configurada uma falha ao recuperar o snapshot é **não-fatal — a task roda mesmo
   assim**, isto é, sem a identidade de quem submeteu. Para `search_docs` isso significa o pior
   defeito que este servidor pode ter: a busca rodando como a APLICAÇÃO, com o trim de ACL
   errado e a trilha gravando `process:app` — sem erro, sem log, sem sintoma. É a mesma falha
   que `caller.identidade_do_chamador` existe para impedir no caminho síncrono. Configurar a
   chave inverte o contrato: qualquer falha de recuperar, decifrar, parsear ou aplicar o
   snapshot — **inclusive um snapshot simplesmente ausente** — passa a FALHAR A TASK.

   Ou seja: a chave não é higiene de segredo com um bônus. Ela é o que faz a task herdar a
   mesma garantia de identidade que a chamada síncrona já tem.

Por isso **as duas juntas ou nada**. Faltando qualquer uma, `indisponivel()` devolve o motivo, a
extensão não é registrada e a tool nasce sem `task=`. A busca continua síncrona — o
comportamento de sempre, byte por byte.

A DEGRADAÇÃO É DECLARADA, NÃO DESCOBERTA, e é o mesmo desenho de `request_state.py`: o servidor
sobe, a capacidade se declara indisponível, e o log diz por quê no boot. A alternativa (recusar
subir) derrubaria cinco superfícies de leitura por causa de uma capacidade opcional.

O NOME DA SEGUNDA VARIÁVEL É DO PACOTE, e isso não é descuido: `fastmcp_tasks.settings` lê o
prefixo `FASTMCP_TASKS_`. Reexportá-la de um nome nosso criaria a configuração que parece
aplicada e não tem efeito — o pacote continuaria lendo a dele, vazia.

═══ O QUE ACONTECE QUANDO A RÉPLICA MORRE ═══

É o cenário que o item existe para cobrir, e vale dito por extenso. O worker roda dentro do
processo do servidor (lifespan da extensão). Com `minReplicas: 0`, a réplica que aceitou a task
pode morrer antes de terminá-la. O que sustenta o cenário é o Redis: o estado da task fica lá, o
`redelivery_timeout` do Docket (300s por padrão) devolve à fila a execução que ficou órfã, e o
próprio `tasks/get` do cliente — que é uma requisição HTTP — acorda uma réplica nova, cujo
worker pega o trabalho de volta. Sem backend durável nada disso existe, que é o item 1 acima.
"""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from app.shared.settings import settings

logger = logging.getLogger(__name__)

#: O texto que vai ao log quando a capacidade não sobe. Fala de CONFIGURAÇÃO DO SERVIDOR, como o
#: de `request_state.py`, porque quem pode resolver é o operador — não quem chama.
MOTIVO_SEM_BACKEND = (
    "tasks indisponíveis: sem MCP_REDIS_URL. O backend padrão do Docket é `memory://` "
    "(single process only) e este app roda com minReplicas: 0 — uma task aceita numa réplica "
    "não existiria na seguinte, depois de o servidor ter prometido TTL ao cliente. A busca "
    "continua síncrona."
)

MOTIVO_SEM_CHAVE = (
    "tasks indisponíveis: o snapshot de contexto iria para o Redis SEM CIFRA "
    "(FASTMCP_TASKS_ENCRYPTION_KEY ausente ou lida tarde demais pelo pacote). Ele carrega o "
    "access token de quem submeteu — e, sem a chave, uma falha ao recuperá-lo faz a task rodar "
    "SEM a identidade do chamador, com o ACL e a trilha errados. A busca continua síncrona."
)


def snapshot_cifrado() -> bool:
    """Se o snapshot vai para o Redis CIFRADO — perguntando ao objeto que o cifra.

    NÃO LÊ A VARIÁVEL DE AMBIENTE, e a diferença não é estilo. `snapshot_codec()` é a função que
    o pacote chama na hora de gravar, e ela decide sobre o singleton `tasks_settings` (avaliado
    no import) com um `lru_cache` por cima. Uma leitura nossa de `os.environ` — ou até um
    `TasksSettings()` construído na hora — responderia sobre o ambiente ATUAL enquanto o pacote
    grava conforme o que ele leu no import. As duas respostas divergem exatamente no caso que
    importa: alguém acerta a variável tarde, este módulo diz "cifrado", e o token do chamador vai
    para o cache em claro.

    Perguntar ao codec é ter UMA resposta. `PlaintextCodec.protected` é `False`,
    `EncryptedCodec.protected` é `True` — medido.

    EFEITO COLATERAL BOM: chamar isto no boot paga aqui o PBKDF2 da derivação da chave (~1s, e
    o resultado fica no `lru_cache` do pacote), em vez de cobrá-lo da primeira task.
    """
    from fastmcp_tasks.encryption import snapshot_codec

    return bool(snapshot_codec().protected)


def indisponivel() -> str | None:
    """`None` quando as tasks podem subir; senão o MOTIVO, no vocabulário do operador."""
    if not settings.mcp_redis_url.strip():
        return MOTIVO_SEM_BACKEND
    if not snapshot_cifrado():
        return MOTIVO_SEM_CHAVE
    return None


def instalar(mcp: FastMCP) -> bool:
    """Registra a extensão de tasks, ou explica no log por que não. Devolve se ligou.

    O BOOLEANO É O CONTRATO COM A COMPOSITION ROOT, e ele existe porque as duas metades TÊM que
    andar juntas: uma tool registrada com `task=True` num servidor SEM a extensão derruba o
    handshake inteiro (`RuntimeError: … require the tasks extension`) — não a chamada, o
    handshake. Devolver o estado daqui é o que impede `main.py` de registrar a tool numa
    configuração em que ela não pode existir.

    A extensão entra ANTES das tools de propósito: é a ordem que o próprio pacote documenta, e
    a que deixa a validação de `task=True` encontrar a extensão já registrada.
    """
    motivo = indisponivel()
    if motivo:
        # `warning` e não `info`: num ambiente que se pretende completo, isto é uma capacidade
        # que não subiu. Num ambiente de dev é ruído esperado — e é por isso que o texto explica
        # o que se perde ("a busca continua síncrona") em vez de só nomear a variável.
        logger.warning(motivo)
        return False

    from fastmcp_tasks import TasksExtension

    # `url=` explícito em vez de deixar o pacote ler o ambiente: a URL é NOSSA (`MCP_REDIS_URL`,
    # que serve também o store de sessão), e depender de `FASTMCP_DOCKET_URL` faria a mesma
    # conexão ser configurada por duas variáveis diferentes, uma por consumidor.
    mcp.add_extension(TasksExtension(url=settings.mcp_redis_url.strip()))
    logger.info("tasks ligadas sobre backend durável — `search_docs` aceita execução em task")
    return True
