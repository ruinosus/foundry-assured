"""O SELO DE ASSURANCE — a garantia deste produto como extensão de protocolo negociada.

É a camada que motivou separar o MCP num app próprio (ADR-027), e a única parte deste produto
que não tem equivalente de primeira parte: um servidor MCP cuja resposta carrega, verificável,
**de onde veio** (as citações) e **que está registrada** (o id do evento na trilha da ADR-023).
A MÁXIMA MAIOR não a alcança pela exceção que o próprio CLAUDE.md calibra — a camada de
assurance é nossa, e foi procurada antes de ser escrita.

O SELO NÃO CALCULA NADA. É a propriedade que o faz valer alguma coisa: cada campo é uma cópia de
algo que já existia antes de a extensão rodar.

    citations  ←  `sources` que a própria tool devolveu (já aparado pelo ACL do chamador)
    audit      ←  o recibo de `audit.public.receipts()`, o evento que a tool gravou

Se algum campo precisasse ser computado aqui, o desenho estaria errado: significaria que a
informação não existe no produto e que alguém teria que acreditar na palavra do selo. Um selo
que recalcula não prova nada — prova a si mesmo.

═══ AS DUAS REGRAS DO PROTOCOLO QUE MUDAM O DESENHO (SEP-2133) ═══

1. **O opt-in é confirmado a cada requisição, ANTES de mudar o que o chamador recebe.** Um
   cliente que não anuncia a extensão tem que receber a resposta idêntica à de antes desta
   fase. Aqui isso é literal: sem opt-in nem a caixa de recibos abre, e `intercept_tool_call`
   devolve o que `call_next()` devolveu, sem tocar em nada. Medido nos dois sentidos por
   `tests/assurance_seal_test.py`, que compara o resultado de fio contra um servidor montado
   SEM a extensão.
2. **Extensões não sobem de servidor montado para o pai** (`FastMCP.add_extension`, docstring:
   "Register extensions on the server you run"). Este app não monta ninguém — `mcp_app.main` É
   a raiz —, então registrar em `register_surfaces` já é registrar na raiz. Fica dito porque no
   dia em que este servidor for montado dentro de outro, a extensão some do fio sem erro.

═══ O IDENTIFICADOR, E POR QUE ESTE ═══

    br.com.rededor.foundry/assurance

Ele vai no fio (`capabilities.extensions[identifier]`) e é contrato com clientes: trocá-lo
depois quebra quem já o anuncia. Por partes:

- `br.com.rededor` — reverse-DNS de `rededor.com.br`, o domínio da organização. A SEP exige
  prefixo reverse-DNS e a validação da própria biblioteca chama isso pelo nome
  (`mcp/shared/extension.py: validate_extension_identifier`); o exemplo canônico do ecossistema
  é `io.modelcontextprotocol/tasks`, que é `modelcontextprotocol.io` invertido.
- `foundry` — o produto. Sem ele, um segundo servidor MCP da mesma organização colidiria no
  mesmo identificador, e colisão de extensão não dá erro: dá dois selos com significados
  diferentes sob a mesma chave.
- `assurance` — o que a extensão é.

DIVERGE DO RASCUNHO DA SPEC (`rededor.com/assurance`) por dois motivos medidos, não de gosto:
aquele é forward-DNS (a SEP pede o inverso), e `rededor.com` não é o domínio da organização
(`rededor.com.br` é) — seria reivindicar namespace alheio num identificador que viaja no fio.

═══ O QUE O SELO NÃO PODE CARREGAR ═══

Metadado SOBRE a resposta, nunca conteúdo novo. As citações já estavam no corpo que o chamador
recebeu (são as mesmas linhas, aparadas pelo ACL dele em `knowledge`), então republicá-las no
`_meta` não revela nada. O evento da trilha entra só como `scope` + `id`: o `detail` do evento
carrega nome de documento e identidade do ator, e nada disso pode atravessar. O `hash` é
`sha256(prev + payload)` — identifica o evento sem descrever o que ele registra.

`tests/assurance_seal_test.py` prova isso com um chamador sem acesso: o trim devolve zero
linhas, o selo sai com zero citações, e o nome do documento reservado não aparece em lugar
nenhum do selo serializado.

═══ ONDE ELE NÃO CHEGA (dito, não escondido) ═══

`intercept_tool_call` é o único gancho de resposta que a `ServerExtension` oferece: ele envolve
`tools/call` e mais nada. O resource `document://` e a completion continuam sem selo — não
porque não mereçam, mas porque o protocolo não tem, nesta versão do pacote, o gancho
equivalente. Quem for atrás disso mede antes de prometer.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.extensions import ServerExtension
from fastmcp.tools.base import InputRequiredToolResult, ToolResult
from mcp_types import CallToolRequestParams

from app.modules.audit.public import receipts

#: O identificador no fio. Ver a seção do docstring: é contrato, não detalhe.
IDENTIFICADOR = "br.com.rededor.foundry/assurance"

#: A chave do selo dentro do `_meta` do resultado. É o mesmo identificador de propósito: um
#: cliente que negociou a extensão sabe procurar exatamente onde ela se chamou.
CHAVE_DO_SELO = IDENTIFICADOR


def _citacoes(resultado: ToolResult) -> list[dict[str, Any]] | None:
    """As citações que a TOOL produziu, ou `None` quando ela não produz citações.

    A diferença entre `[]` e `None` é a diferença entre "o trim de ACL não deixou nada passar"
    e "esta tool não fundamenta nada" — e o selo não pode confundir as duas. Uma tool sem o
    campo `sources` não ganha a chave `citations` no selo: inventar `citations: []` para ela
    afirmaria, falsamente, que ela tentou citar e não conseguiu.
    """
    estruturado = resultado.structured_content
    if not isinstance(estruturado, dict):
        return None
    fontes = estruturado.get("sources")
    if not isinstance(fontes, list):
        return None
    # Cópia rasa dos campos que a tool já publicou. Nada é derivado: `source` e `url` são os
    # mesmos valores que o chamador acabou de receber no corpo.
    return [
        {"source": f.get("source"), "url": f.get("url")}
        for f in fontes
        if isinstance(f, dict)
    ]


def _trilha(recibos: list[dict]) -> list[dict[str, str]]:
    """Os eventos que a chamada gravou, reduzidos ao que pode viajar: escopo, tipo e id.

    O recibo vem inteiro de `audit.receipts()` (é o evento que `record` devolveu, mais a
    partição em que foi gravado), e é AQUI que ele é aparado — ver a seção "o que o selo não
    pode carregar" no topo. `detail`, `actor`, `summary` e `ref` ficam de fora: os quatro
    descrevem o que foi lido e por quem.

    `scope` + `id` é o par que localiza o evento para quem for verificar; `kind` vem do
    vocabulário fechado da trilha (`audit.KINDS`) e diz que CLASSE de evento é, sem descrever
    nenhum.
    """
    saida = []
    for recibo in recibos:
        evento = recibo.get("event") or {}
        if evento.get("hash"):
            saida.append(
                {
                    "scope": str(recibo.get("scope", "")),
                    "kind": str(evento.get("kind", "")),
                    "id": str(evento["hash"]),
                }
            )
    return saida


class SeloDeAssurance(ServerExtension):
    """A extensão. `identifier` é obrigatório na classe-base (não tem default) — ver o topo."""

    identifier = IDENTIFICADOR

    def settings(self) -> dict[str, Any]:
        """O que este servidor oferece, anunciado por capacidade em `capabilities.extensions`.

        Anunciar por capacidade (e não só o identificador nu) é o que permite a um cliente
        decidir se vale a pena negociar: ele lê daqui que o selo traz citações e referência de
        trilha, sem ter que chamar uma tool para descobrir.

        `version` é do SELO, não do produto: o dia em que a forma do selo mudar de maneira
        incompatível, este número sobe e um cliente antigo sabe que não entende o que recebeu.
        """
        return {"version": 1, "citations": True, "audit_trail": True}

    def _opt_in(self, context: Any) -> dict[str, Any] | None:
        """As configurações que o CLIENTE declarou para esta extensão nesta requisição, ou
        `None` quando ele não a declarou.

        A extensão negocia POR REQUISIÇÃO (SEP-2133: o cliente repete as capacidades dele no
        `_meta` de cada request), então a pergunta é feita a cada chamada e não uma vez na
        sessão. `client_settings` quer o `ServerRequestContext` do SDK; o que chega ao
        interceptador é o `Context` do FastMCP, e `_srctx` é a escotilha que a própria
        biblioteca documenta e usa (`fastmcp/server/dependencies.py:85`,
        `fastmcp/server/context.py:535`).

        Sem contexto de requisição, a resposta é `None` — isto é, NÃO carimba. Falhar para o
        lado de não mudar a resposta é o único lado seguro aqui: carimbar um cliente que não
        pediu é exatamente o que a regra 1 do protocolo proíbe.
        """
        rc = getattr(context, "request_context", None)
        srctx = getattr(rc, "_srctx", None) if rc is not None else None
        if srctx is None:
            return None
        return self.client_settings(srctx)

    async def intercept_tool_call(self, params: CallToolRequestParams, context: Any, call_next):
        """Anexa o selo ao `_meta` do resultado — e só a quem negociou a extensão.

        O CAMINHO SEM OPT-IN É A PRIMEIRA LINHA, e é literalmente `return await call_next()`.
        Nem a caixa de recibos abre. É o que faz a resposta ser idêntica à de antes desta fase
        em vez de "equivalente": não há nenhum ponto do fluxo em que um objeto tenha sido
        tocado e depois restaurado.

        POR QUE O `_meta` E NÃO O CORPO. `ToolResult.meta` vira o `_meta` do `CallToolResult`
        (`fastmcp/tools/base.py: to_mcp_result`) — e, medido, com `meta is None` o resultado
        nem passa pelo ramo do `CallToolResult`: o servidor devolve o par
        `(content, structured_content)` cru. Mexer no corpo mudaria o payload que o modelo do
        cliente lê, e um selo que altera a resposta não é um selo, é uma edição.
        """
        if self._opt_in(context) is None:
            return await call_next()

        # A caixa desce para a task do handler pelo ContextVar e volta preenchida — ver a
        # docstring de `audit.public.receipts`, que explica por que o sentido é esse.
        with receipts() as recibos:
            resultado = await call_next()

        # `ToolCallOutcome` também admite um `BaseModel` de outra extensão (um short-circuit),
        # e `InputRequiredToolResult` é um `ToolResult` cujo contrato diz que `content` e
        # `structured_content` não carregam nada (SEP-2322). Carimbar qualquer um dos dois seria
        # afirmar procedência sobre uma resposta que não é uma resposta.
        if not isinstance(resultado, ToolResult) or isinstance(resultado, InputRequiredToolResult):
            return resultado

        selo: dict[str, Any] = {"version": 1}
        citacoes = _citacoes(resultado)
        if citacoes is not None:
            selo["citations"] = citacoes
        trilha = _trilha(recibos)
        if trilha:
            selo["audit"] = trilha

        resultado.meta = {**(resultado.meta or {}), CHAVE_DO_SELO: selo}
        return resultado


def register(mcp: FastMCP) -> None:
    """Registra o selo NA RAIZ. Chamado por `mcp_app.main.register_surfaces`.

    Existe como função (em vez de duas linhas em `main.py`) pelo mesmo motivo que
    `register_surfaces` existe: o gate de instrumentação monta o servidor pela MESMA fiação que
    o app monta, e uma extensão registrada só no `build_app` passaria despercebida por ele.
    """
    mcp.add_extension(SeloDeAssurance())
