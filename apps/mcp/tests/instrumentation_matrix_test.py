"""Toda superfície MCP é autenticada por papel e DECLARA o que grava — o gêmeo, neste app, do
gate `tests/architecture/instrumentation_matrix_test.py` do monolito.

POR QUE ESTE GATE EXISTE AQUI TAMBÉM. A Fase 0c tirou a linha `/mcp` da matriz do monolito — o
comentário que ficou no lugar dela diz, corretamente, que a superfície é `apps/mcp` agora e que
"a de lá é coberta pelos gates de `apps/mcp/tests/`". Isso nunca foi verdade: nenhum teste deste
app perguntava "toda tool tem `auth=`?" nem "toda tool que existe está declarada em algum
lugar?" — as duas metades que a matriz do monolito prova. `identity_passthrough_test` prova, de
lado, que a ÚNICA tool de hoje (`search_docs`) grava citação e trilha — mas prova por ter escrito
o teste à mão, não por um mecanismo que reprova sozinho quando uma tool NOVA esquece uma das
duas. Este arquivo é esse mecanismo.

SUPERFÍCIE NÃO É SÓ TOOL — E ISSO MUDOU NA FASE 1. O servidor passou a publicar PROMPTS (as
instruções compostas dos documentos AgentSchema) e um RESOURCE template (o documento integral,
com o ACL do backend). Os dois são superfície pelo mesmo motivo que uma tool é: aparecem na
listagem de um cliente autenticado e devolvem conteúdo. Uma matriz que só olhasse tools ficaria
verde sobre um resource sem `auth=` — e o resource é justamente o que serve documento controlado
por ACL. `_superficies()` descobre as famílias.

E A QUARTA FAMÍLIA É A COMPLETION, QUE NENHUMA ENUMERAÇÃO DE COMPONENTE ALCANÇA. `completion/
complete` não é um componente do FastMCP: é UM handler por servidor (`mcp._completion_handler`),
sem campo `auth=` e sem check nenhum rodado por cima dele (`_on_complete` em
`fastmcp/server/mixins/mcp_operations.py`). Enquanto esta matriz enumerava só tool/prompt/
resource, ela afirmava "toda superfície exige papel do Entra" sobre uma superfície que não via —
e a afirmação era falsa: medido, um token válido com `roles: []` recebia
`['runbook-secreto.md']` da completion. O gate agora mora PENDURADO no handler
(`resources_knowledge.completar.auth`), que é o mesmo objeto que ele executa a cada chamada — não
uma declaração ao lado do código, que poderia divergir dele. É lá que `_registro_cru` olha.

E A FASE 2 TROUXE UMA COISA QUE NÃO É SUPERFÍCIE E MESMO ASSIM PRECISA SER VISTA: a EXTENSÃO de
protocolo (SEP-2133) que carimba o selo de assurance. Ela não responde a método nenhum, não
aparece em listagem e não tem campo `auth=` — mas MUDA o que sai no fio de toda resposta de tool
para quem a negociou. A instrução desta série é que superfície nova entra na matriz no mesmo
commit em que nasce; o veredito aqui é que a extensão entra na matriz (é declarada, e pelo
identificador inteiro, porque ele é contrato de fio) mas NÃO na checagem de `auth=`. O que a
vigia no lugar está escrito em `_extensoes`, junto com o motivo de isso não ser uma exceção
disfarçada.

COMO OS PROMPTS ENTRAM SEM VIRAR UMA SEGUNDA LISTA. Enumerar os dez prompts nesta matriz seria
recriar, aqui, a lista que `tests/prompts_mirror_test.py` existe para impedir — e ela divergiria
no primeiro agente novo. Então a matriz declara a FAMÍLIA (`prompt:*`), e o cruzamento aceita um
prompt como declarado somente se o id dele for um dos que `prompts_agentdefs.prompt_ids()`
deriva. Um prompt escrito à mão (id que o `agentdefs` não compõe) não cai na família: ele aparece
individualmente como não declarado, e o gate fica vermelho. As duas regras se reforçam em vez de
se repetir.

O CUIDADO QUE A VERSÃO DO MONOLITO NÃO TEVE, E A FORMA ESPELHADA QUE A ARMADILHA TOMA AQUI. Lá,
uma rota sem auth se tornava invisível à captura (perdia `.methods`), e "nenhuma sem auth"
passava vazio sobre zero rotas olhadas. Aqui a armadilha é a MESMA ideia com o sinal trocado —
medida, não deduzida (ver `_prova_por_mutacao`): `FastMCP.list_tools()` só filtra a tool que TEM
`auth=` e falha o check (ela some quando não há contexto autorizado); uma tool que ESQUECEU
`auth=` nunca é filtrada e continua sempre visível. Ou seja, descobrir tools por
`mcp.list_tools()` sem contexto faz o CONTRÁRIO do que se espera: a tool bem configurada
(`search_docs`) desaparece da contagem, e a mal configurada permanece — corrompendo exatamente o
cruzamento que a verificação 2 (declarada vs. encontrada) depende para pegar drift. Por isso a
descoberta usa `Provider.list_*(mcp)` — os métodos da CLASSE-BASE, chamados sem passar pelo
override do `FastMCP` — que devolvem o registro CRU, com `.auth` do jeito que o registro deixou,
filtro nenhum aplicado.

    uv run python -m tests.instrumentation_matrix_test
"""

from __future__ import annotations

import sys

#: As colunas que a matriz do monolito usa. Nenhuma superfície daqui é um agente conversacional,
#: então a maioria é `n/a` — e o texto do `n/a` é a justificativa, não um placeholder.
COLUNAS = ("conversa", "tokens", "referencias", "chamado", "trilha", "caso_de_uso")

#: A chave que representa TODOS os prompts derivados do `agentdefs`. Ver a nota no topo: a lista
#: de ids não pode morar aqui.
FAMILIA_PROMPTS = "prompt:*"

#: A chave da COMPLETION. É família e não um id porque o FastMCP admite UM handler por servidor:
#: nomear a linha pela função de hoje faria a matriz ficar órfã num rename, sem que nada tivesse
#: mudado de fato na superfície.
FAMILIA_COMPLETION = "completion:*"

#: A EXTENSÃO. Aqui a chave é o IDENTIFICADOR INTEIRO, ao contrário das outras três — e a
#: diferença é o ponto: o identificador de uma extensão é contrato de fio (SEP-2133), então
#: trocá-lo TEM que ficar vermelho aqui. Uma família `extension:*` deixaria passar exatamente a
#: mudança que quebra clientes.
EXTENSAO_SELO = "extension:br.com.rededor.foundry/assurance"

#: A MATRIZ. Uma linha por superfície registrada hoje. `True` = grava hoje; string = não grava, e
#: o texto diz por quê (mesma convenção do monolito).
MATRIZ: dict[str, dict[str, object]] = {
    "tool:search_docs": {
        "conversa": "n/a: chamada de tool avulsa — não há objeto de conversa para persistir",
        "tokens": "n/a: search_docs só busca, não chama modelo — não há uso de token a contar",
        # Regra 4 (CLAUDE.md): toda resposta fundamentada carrega citação. `identity_passthrough_test`
        # trava isto linha a linha — `sources` presente, e vazio honesto (não prosa sem fonte)
        # quando o trim de ACL não deixa nada passar.
        "referencias": True,
        "chamado": "n/a: search_docs não abre chamado",
        # ADR-023: o ator da trilha é QUEM PERGUNTOU, não `process:app` — gravado dentro de
        # `retrieve` via `audit.actor()`, que lê o `_Chamador` que `search_docs` declara antes de
        # buscar. `identity_passthrough_test` trava os dois lados (com token e sem).
        "trilha": True,
        "caso_de_uso": "n/a: módulo usecases não se aplica a uma busca avulsa por MCP",
    },
    "tool:open_ticket": {
        "conversa": "n/a: escrita avulsa por tool — não há objeto de conversa para persistir",
        "tokens": "n/a: não chama modelo; quem redigiu o resumo foi o cliente",
        # A resposta é o RECIBO da própria escrita: o `ticket.id` que ela devolve é a referência,
        # e não há afirmação sobre a base de conhecimento a fundamentar. A regra 4 vale para quem
        # AFIRMA coisas sobre o corpus; esta tool só relata o que gravou. O que a sustenta é a
        # coluna ao lado (trilha), não uma citação.
        "referencias": "n/a: a resposta é o recibo da própria escrita — o `ticket.id` É a "
        "referência, e nada é afirmado sobre a base",
        # A ÚNICA LINHA DESTA MATRIZ COM `chamado: True`. É a fase inteira em uma célula.
        "chamado": True,
        # DOIS eventos por escrita aprovada, e são de perguntas diferentes: `hitl.decide` grava a
        # DECISÃO (quem decidiu o quê, com que papel, e — no `edit` — que campos corrigiu) em
        # `approvals`; `create_ticket` grava a ESCRITA (o id, a severidade, o domínio) no mesmo
        # escopo. Um sem o outro não sustenta a regra 5: a decisão sem a escrita não prova que
        # algo aconteceu, e a escrita sem a decisão é exatamente o que não pode existir.
        "trilha": True,
        "caso_de_uso": "n/a: módulo usecases não se aplica à abertura de um chamado avulso",
    },
    "resource:document://{domain}/{name}": {
        "conversa": "n/a: leitura avulsa de documento — não há conversa para persistir",
        "tokens": "n/a: serve o blob, não chama modelo — não há uso de token a contar",
        # O recurso É a fonte: a URI identifica o documento e o corpo devolve o `url` do blob que
        # respondeu. Não há resposta a fundamentar, então não há citação a anexar — a regra 4
        # vale para quem AFIRMA coisas, e este endpoint só entrega o original.
        "referencias": "n/a: o recurso é a própria fonte — a URI e o `url` do blob são a citação",
        "chamado": "n/a: leitura, nunca escrita — este resource não abre chamado",
        # ADR-023, e o PAR completo: a leitura autorizada e a NEGADA, que é o sinal mais
        # interessante da trilha. `resource_document_test` trava os dois.
        "trilha": True,
        "caso_de_uso": "n/a: módulo usecases não se aplica à leitura de um documento",
    },
    FAMILIA_COMPLETION: {
        "conversa": "n/a: autocompletar um argumento — não há conversa para persistir",
        "tokens": "n/a: sugere a partir do índice, não chama modelo — não há token a contar",
        "referencias": "n/a: devolve NOMES de documento; não afirma nada sobre o conteúdo deles, "
        "então não há resposta a fundamentar",
        "chamado": "n/a: sugestão de texto, nunca escrita",
        # ADR-023: a sugestão de NOME passa pelo MESMO `retrieve` da tool, e é lá dentro que a
        # leitura é registrada sob a identidade do chamador (`audit.actor()` lê o `Chamador` que
        # a completion declara antes de buscar). A sugestão de DOMÍNIO não toca conteúdo nenhum —
        # lê o catálogo —, então não há acesso a registrar nela.
        "trilha": True,
        "caso_de_uso": "n/a: módulo usecases não se aplica a um autocompletar",
    },
    EXTENSAO_SELO: {
        "conversa": "n/a: envolve uma chamada de tool avulsa — não há conversa para persistir",
        "tokens": "n/a: o selo copia o que a tool devolveu; não chama modelo",
        # É A RAZÃO DE ELE EXISTIR: as citações que a tool produziu viajam no `_meta` da
        # resposta, em forma estável de protocolo, para o cliente que negociou a extensão.
        # Regra 4 do CLAUDE.md continua sendo da TOOL — o selo torna verificável, não substitui.
        "referencias": True,
        "chamado": "n/a: o selo observa e anexa metadado; não executa nada, muito menos escrita",
        # NÃO é `True`: o selo REFERENCIA o evento que a tool gravou (ADR-023), com escopo e id,
        # e não grava um segundo. Gravar um evento por resposta duplicaria a trilha do mesmo
        # acesso — e o que se quer provar é que a leitura está registrada, não que o selo rodou.
        "trilha": "n/a: referencia o evento que a tool gravou (escopo + id); não grava nenhum — "
        "um segundo evento por resposta duplicaria a trilha do mesmo acesso",
        "caso_de_uso": "n/a: módulo usecases não se aplica a metadado de resposta",
    },
    FAMILIA_PROMPTS: {
        "conversa": "n/a: um prompt é instrução publicada, não uma conversa",
        "tokens": "n/a: publicar o texto não chama modelo — quem gasta token é o cliente depois",
        "referencias": "n/a: instrução do produto, não resposta sobre a base — nada a citar",
        "chamado": "n/a: prompts não executam nada, muito menos escrita",
        # LACUNA CONHECIDA, não `n/a`: ler um prompt é ler uma DEFINIÇÃO do produto (documento
        # AgentSchema versionado no repositório), não conteúdo controlado por ACL — a trilha da
        # ADR-023 registra acesso a conteúdo. Fica declarado como lacuna, e não como "não se
        # aplica", porque no dia em que um prompt carregar dado de tenant a resposta muda.
        "trilha": "lacuna: leitura de definição do produto, não de conteúdo controlado — "
        "revisitar se um prompt passar a carregar dado de tenant",
        "caso_de_uso": "n/a: módulo usecases não se aplica à publicação de instruções",
    },
}


def _sem_auth(superficies) -> list[str]:
    """Ids das superfícies SEM `auth=` — a checagem estrutural, isolada para o teste de mutação
    poder chamar a mesma função contra um registro descartável."""
    return sorted(sid for sid, _nome, auth in superficies if auth is None)


async def _registro_cru(mcp) -> list[tuple[str, str, object]]:
    """Toda superfície registrada, TAL COMO FOI FEITA, sem o filtro de auth que os `list_*` do
    `FastMCP` aplicam antes de devolver — ver a nota grande no topo do arquivo.

    Devolve `(id da superfície, nome cru, auth)`. O id carrega a família no prefixo, porque uma
    tool e um prompt podem ter o mesmo nome e não são a mesma superfície.
    """
    from fastmcp.server.providers.base import Provider

    achadas: list[tuple[str, str, object]] = []
    for t in await Provider.list_tools(mcp):
        achadas.append((f"tool:{t.name}", t.name, t.auth))
    for p in await Provider.list_prompts(mcp):
        achadas.append((f"prompt:{p.name}", p.name, p.auth))
    for r in await Provider.list_resources(mcp):
        achadas.append((f"resource:{r.uri}", str(r.uri), r.auth))
    for rt in await Provider.list_resource_templates(mcp):
        achadas.append((f"resource:{rt.uri_template}", rt.uri_template, rt.auth))
    # A COMPLETION não é componente: é um handler solto no servidor, e o FastMCP não guarda
    # `auth=` para ele (nem roda check algum). O gate dela viaja no atributo `.auth` do próprio
    # handler — o mesmo objeto que ele executa —, então é daí que a coluna sai. Um handler que
    # perdeu o gate perde o atributo, e cai na verificação 1 como qualquer outra superfície.
    handler = getattr(mcp, "_completion_handler", None)
    if handler is not None:
        nome = getattr(handler, "__name__", repr(handler))
        achadas.append((f"completion:{nome}", nome, getattr(handler, "auth", None)))
    return achadas


def _extensoes(mcp) -> list[str]:
    """As extensões de protocolo registradas na RAIZ deste servidor, pelo identificador de fio.

    POR QUE UMA EXTENSÃO ENTRA NESTA MATRIZ, sendo que não é uma superfície. Ela não responde a
    método nenhum e não devolve conteúdo próprio — mas MUDA o que sai no fio de toda resposta de
    tool, para quem a negociou. A matriz existe para responder "o que este servidor entrega e o
    que ele registra"; uma extensão que altera a resposta e não aparecesse aqui deixaria a
    pergunta sem resposta justamente na camada que o produto vende.

    E POR QUE ELA NÃO ENTRA NA VERIFICAÇÃO 1 (`auth=`). Extensão não tem campo `auth=` — não é
    componente, é um envelope em volta do `tools/call`. O que a governa são duas coisas
    medidas, não uma declaração: ela só roda como parte de uma chamada de tool, e a tool carrega
    o gate de papel do Entra (verificação 1, sobre `tool:search_docs`); e o que ela anexa é
    cópia do que aquela mesma chamada já devolveu ao mesmo chamador — provado, com um chamador
    sem acesso, em `tests/assurance_seal_test.py`. Enfiá-la em `_sem_auth` só produziria um
    `auth=None` que teria de ser dispensado com uma exceção; declarar aqui o que a vigia no
    lugar é mais honesto que uma exceção.

    Lê `mcp._extensions`, que é onde `add_extension` guarda o registro — não uma lista nossa em
    paralelo, que divergiria na primeira extensão nova.
    """
    return sorted(f"extension:{i}" for i in getattr(mcp, "_extensions", {}))


def _declarado(sid: str, derivados: frozenset[str]) -> str:
    """A chave da matriz que responde por esta superfície.

    Um prompt cujo id o `agentdefs` deriva responde pela FAMÍLIA; qualquer outro responde por si
    mesmo — e, como ninguém o declarou individualmente, aparece como não declarado. É assim que
    um prompt escrito à mão fica vermelho aqui, além de ficar vermelho no gate espelhado.
    """
    if sid.startswith("prompt:") and sid.removeprefix("prompt:") in derivados:
        return FAMILIA_PROMPTS
    if sid.startswith("completion:"):
        return FAMILIA_COMPLETION
    return sid


async def _prova_por_mutacao() -> str | None:
    """Registra, num servidor descartável, uma superfície de CADA família sem `auth=` (o defeito
    que a verificação 1 tem que pegar) e uma de cada COM `auth=` (o controle), e mostra duas
    coisas medidas, não afirmadas:

    1. `_sem_auth` sobre o registro CRU acha exatamente as quatro sem dono — tool, prompt,
       resource E completion. Antes da Fase 1 esta prova só cobria tool: um resource sem `auth=`
       passaria. E até este conserto ela não cobria a completion, que é a superfície onde a falta
       de gate foi de fato MEDIDA em produção do teste (roles vazios, sugestões devolvidas).
    2. A listagem FILTRADA (`FastMCP.list_tools()`, sem contexto de auth) faz o oposto do que se
       esperaria: perde a tool COM dono (ela falha no check de auth e é removida) e MANTÉM a tool
       sem dono (que nunca é checada, porque `auth is None` pula o filtro). É a prova de que
       descobrir por aí, em vez de pelo registro cru, corromperia o cruzamento da verificação 2.

    Devolve a mensagem de falha, ou `None` se as mutações foram corretamente pegas.
    """
    from fastmcp import FastMCP

    from mcp_app.auth import require_any_role

    descartavel = FastMCP("mutação-descartável", tools=[])
    dono = require_any_role("Reader")

    def tool_sem_dono() -> str:
        return "nunca deveria existir sem auth="

    def tool_com_dono() -> str:
        return "o controle — representa search_docs"

    def prompt_sem_dono() -> str:
        return "prompt sem auth="

    def prompt_com_dono() -> str:
        return "o controle — representa os prompts do agentdefs"

    def recurso_sem_dono(x: str) -> str:
        return x

    def recurso_com_dono(x: str) -> str:
        return x

    descartavel.tool(tool_sem_dono, name="tool_sem_dono")  # sem `auth=`, de propósito
    descartavel.tool(tool_com_dono, name="tool_com_dono", auth=dono)
    descartavel.prompt(prompt_sem_dono, name="prompt_sem_dono")
    descartavel.prompt(prompt_com_dono, name="prompt_com_dono", auth=dono)
    descartavel.resource("sem://{x}", name="recurso_sem_dono")(recurso_sem_dono)
    descartavel.resource("com://{x}", name="recurso_com_dono", auth=dono)(recurso_com_dono)

    # A COMPLETION é UMA por servidor, então a mutação registra a versão SEM gate — que é
    # exatamente o defeito real que existia: um handler sem `.auth`. O controle (o handler COM
    # gate) é o servidor de verdade, medido na verificação 1 logo acima desta prova.
    async def completar_sem_dono(ref, argument, context):
        return []

    descartavel.completion(completar_sem_dono)

    cru = await _registro_cru(descartavel)
    achadas = _sem_auth(cru)
    esperadas = [
        "completion:completar_sem_dono",
        "prompt:prompt_sem_dono",
        "resource:sem://{x}",
        "tool:tool_sem_dono",
    ]
    if achadas != esperadas:
        return (
            "a mutação não reproduziu o defeito esperado no registro cru — "
            f"achadas={achadas!r} (esperava {esperadas!r})"
        )

    # A superfície nova MAL DECLARADA: `recurso_sem_dono` também não está em MATRIZ, e o
    # cruzamento da verificação 2 tem que enxergá-la como não declarada.
    derivados = frozenset()
    nao_declaradas = sorted(
        {_declarado(sid, derivados) for sid, _n, _a in cru} - set(MATRIZ)
    )
    if "resource:sem://{x}" not in nao_declaradas:
        return (
            "uma superfície NOVA não declarada passou pelo cruzamento — "
            f"não declaradas={nao_declaradas!r}"
        )

    filtrada = sorted(t.name for t in await descartavel.list_tools())
    if filtrada != ["tool_sem_dono"]:
        return (
            "a listagem filtrada deveria perder a tool COM auth e manter a SEM auth "
            f"(a armadilha) — veio {filtrada!r}"
        )

    return None


async def _superficies() -> tuple[list[tuple[str, str, object]], list[str]]:
    """O que este servidor publica HOJE pela composition root real (`mcp_app.main`), com a MESMA
    fiação que `build_app()` usa — nada de registrar à mão aqui, ou o teste provaria a superfície
    que ELE monta, não a que o app monta. É por isso que `register_surfaces` existe como função
    em `main.py`.

    Devolve os componentes (com o `auth=` cru) e as EXTENSÕES, separados: as duas listas
    respondem à mesma pergunta da matriz, mas só a primeira tem campo `auth=` para checar — ver
    `_extensoes`."""
    from app.shared.settings import settings
    from mcp_app.auth import build_auth
    from mcp_app.main import build_mcp, register_surfaces, wire_registry

    wire_registry()
    mcp = build_mcp(build_auth(settings.mcp_public_base_url))
    register_surfaces(mcp)
    return await _registro_cru(mcp), _extensoes(mcp)


def main() -> int:
    import asyncio

    from app.shared.settings import settings
    from mcp_app.prompts_agentdefs import prompt_ids

    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    original = (
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.mcp_public_base_url,
    )
    try:
        # Auth LIGADA para a descoberta: sem `ENTRA_*` a superfície nasce sem `auth=` nenhum (dev
        # local degrada aberto — ver `require_any_role`), e a verificação 2 abaixo não
        # significaria nada.
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        settings.mcp_public_base_url = "http://testserver"

        superficies, extensoes = asyncio.run(_superficies())
        derivados = frozenset(prompt_ids())
        ids = sorted(sid for sid, _n, _a in superficies)
        por_familia: dict[str, int] = {}
        for sid in ids:
            por_familia[sid.split(":", 1)[0]] = por_familia.get(sid.split(":", 1)[0], 0) + 1
        resumo = ", ".join(f"{k}={v}" for k, v in sorted(por_familia.items()))
        check(f"a descoberta achou superfícies ({len(ids)}: {resumo})", len(ids) >= 1)
        check(
            "as quatro famílias estão presentes (tool, prompt, resource, completion)",
            set(por_familia) == {"tool", "prompt", "resource", "completion"},
        )

        # --- 1 · toda superfície exige papel do Entra ---------------------------------------
        sem_auth = _sem_auth(superficies)
        check(
            "nenhuma superfície sem `auth=`"
            + (f" — SEM AUTH: {', '.join(sem_auth)}" if sem_auth else ""),
            not sem_auth,
        )

        # --- prova de que a verificação acima SABE falhar (não é vácuo por filtro) ----------
        problema_mutacao = asyncio.run(_prova_por_mutacao())
        check(
            "a checagem 1 é capaz de reprovar em TODA família (provado por mutação)"
            + (f" — {problema_mutacao}" if problema_mutacao else ""),
            problema_mutacao is None,
        )

        # --- 1b · a extensão de protocolo é VISTA pela matriz --------------------------------
        # Ela não passa pela checagem de `auth=` (ver `_extensoes`), mas passa pela de
        # declaração: uma extensão registrada e não declarada — ou um identificador trocado,
        # que é quebra de contrato de fio — fica vermelha na verificação 2 logo abaixo.
        check(
            f"a extensão de protocolo foi descoberta ({', '.join(extensoes) or 'NENHUMA'})",
            extensoes == [EXTENSAO_SELO],
        )

        # --- 2 · nenhuma superfície órfã, dos dois lados ------------------------------------
        respondidas = {_declarado(sid, derivados) for sid in ids} | set(extensoes)
        nao_declaradas = sorted(respondidas - set(MATRIZ))
        check(
            "toda superfície registrada está declarada na matriz"
            + (f" — FALTAM: {', '.join(nao_declaradas)}" if nao_declaradas else ""),
            not nao_declaradas,
        )
        orfas = sorted(set(MATRIZ) - respondidas)
        check(
            "nenhuma declaração aponta para superfície inexistente"
            + (f" — ÓRFÃS: {', '.join(orfas)}" if orfas else ""),
            not orfas,
        )

        # --- 3 · toda declaração responde a TODAS as colunas, e `n/a` tem motivo -----------
        incompletas: list[str] = []
        vazias: list[str] = []
        for nome, linha in MATRIZ.items():
            faltando = [c for c in COLUNAS if c not in linha]
            if faltando:
                incompletas.append(f"{nome}: {', '.join(faltando)}")
            for coluna, valor in linha.items():
                if valor is not True and not str(valor).strip():
                    vazias.append(f"{nome}.{coluna}")
        check(
            "toda linha responde a todas as colunas"
            + (f" — INCOMPLETAS: {'; '.join(incompletas)}" if incompletas else ""),
            not incompletas,
        )
        check(
            "toda lacuna declarada tem motivo escrito"
            + (f" — VAZIAS: {', '.join(vazias)}" if vazias else ""),
            not vazias,
        )
    finally:
        (
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.mcp_public_base_url,
        ) = original

    total = len(MATRIZ) * len(COLUNAS)
    grava = sum(1 for l in MATRIZ.values() for v in l.values() if v is True)
    na = sum(1 for l in MATRIZ.values() for v in l.values() if str(v).startswith("n/a:"))
    lacuna = total - grava - na
    print(f"\n  cobertura: {grava}/{total} gravam · {na} não se aplicam · {lacuna} lacunas conhecidas")

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ toda superfície MCP exige papel do Entra e declara o que grava.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
