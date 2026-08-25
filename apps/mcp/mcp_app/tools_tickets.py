"""A tool `open_ticket` — a primeira ESCRITA por MCP, e o contrato de decisão que não se rebaixa.

Tudo o que este servidor fazia até aqui era LER. Esta é a superfície onde a regra 5 do projeto
deixa de ser teoria: *`create_ticket` só dispara após aprovação humana explícita, e a aprovação
exige o papel Approver (ou Admin)*.

═══ O DESENHO: O TRANSPORTE É DO PROTOCOLO, O VOCABULÁRIO É NOSSO ═══

O padrão nativo do protocolo é **aceitar-ou-recusar**: `ElicitResult.action` admite
`accept | decline | cancel`, e é com isso que a maioria dos servidores expressa aprovação. O
contrato deste produto (ADR-019) tem **quatro** decisões — aprovar · **editar** · rejeitar ·
responder — e o `edit` é a razão de aquela ADR existir: *abrir um chamado cujo resumo está
errado, porque recusar era a única alternativa, não é supervisão*.

Rebaixar as quatro a um booleano seria o pior desfecho possível desta fase, então a divisão é:

    TRANSPORTE   `InputRequiredResult` (SEP-2322) — a tool devolve a pergunta e é RECHAMADA
                 com a resposta. Duas rodadas de `tools/call`, sem canal paralelo.
    VOCABULÁRIO  `app.modules.hitl.public.decide` — o MESMO que a escalação do helpdesk usa.
                 As quatro decisões viajam no `requested_schema` do `ElicitRequestFormParams`,
                 como um `enum` de quatro valores, e chegam aqui inteiras.

O `action` do protocolo continua existindo e continua significando o que significa: `accept` é
"o humano preencheu o formulário" — a decisão está DENTRO do formulário, não no `action`.
`decline` e `cancel` são paradas, e parada é sempre permitida (nenhuma escreve nada).

═══ POR QUE A ESCRITA É INALCANÇÁVEL SEM A DECISÃO ═══

Não há tool de criação separada: `open_ticket` é a única, e ela é uma *guard tool*. Na primeira
rodada não existe caminho que chegue ao `create_ticket` — o corpo devolve a pergunta antes.
Na segunda rodada, o corpo só segue se DUAS coisas chegarem juntas:

1. `ctx.input_responses` com a resposta do aprovador, e
2. `ctx.request_state` igual à marca que ESTE servidor emitiu.

A segunda é o que impede um cliente de pular a pergunta. O `request_state` é selado pelo
`RequestStateBoundary` (AES-256-GCM, ligado ao principal autenticado, ao nome da tool, ao digest
dos argumentos e a um TTL) — medido: mandar respostas SEM estado devolve a pergunta de novo, e
mandar um estado forjado ou em texto puro é recusado no fio como
`Invalid or expired requestState`, antes de o corpo rodar. Ver `mcp_app.request_state`.

O QUE ISTO NÃO PROVA, e é dito porque calar seria pior: o protocolo não prova que existe um
humano do outro lado. `input_responses` vêm do cliente, e o cliente É o agente do usuário — um
cliente malicioso pode fabricar a resposta sem mostrar nada a ninguém. O que o produto exige,
e o que de fato barra, é o PAPEL: o `roles` do token do Entra, que o cliente não escreve. Por
isso a regra 5 pede as duas coisas — decisão explícita **e** papel — e não uma delas.

═══ O GATE DE PAPEL, DUAS VEZES, DE PROPÓSITO ═══

`auth=require_any_role("Approver", "Admin")` faz a tool não EXISTIR para quem não pode decidir
(componente negado por `auth=` é filtrado do `tools/list`, não recusado). E `hitl.decide`
recusa de novo, lá dentro, lendo o mesmo claim pelo contextvar que `caller` declara. Não é
redundância decorativa: é a segunda que GRAVA a decisão na trilha (ADR-023) e é a que continua
valendo se alguém um dia registrar esta tool sem `auth=` — o gate de instrumentação pega a
falta, e este segundo gate impede que ela vire uma escrita.

Nada de regra nova aqui: `require_any_role` é o mesmo de `search_docs`, `recusa_de_tenant` é o
mesmo de `tenant_gate` (ADR-010) e `create_ticket` é o mesmo dos outros quatro caminhos que
abrem chamado. Uma regra, mais um consumidor — nunca uma cópia.
"""

from __future__ import annotations

from typing import Any

import mcp_types
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token, get_context

from app.modules.hitl.public import ApprovalRequest, NotAuthorized, decide
from app.modules.tickets.public import create_ticket
from mcp_app import request_state
from mcp_app.auth import require_any_role
from mcp_app.caller import identidade_do_chamador
from mcp_app.tenant_gate import recusa_de_tenant

#: As QUATRO decisões da ADR-019, na ordem em que a ADR as lista. É a lista que vai para o
#: `enum` do formulário E para `allowed_decisions` do pedido — uma só, porque duas divergiriam
#: em silêncio: o formulário ofereceria uma opção que `decide` recusaria depois do humano
#: já ter escolhido.
DECISOES: tuple[str, ...] = ("approve", "edit", "reject", "respond")

#: Os campos que o aprovador pode CORRIGIR num `edit`. `domain` fica de fora de propósito: é
#: atribuição, não conteúdo — `create_ticket` já o recebe como keyword-only justamente para que
#: quem escreve o texto não escolha a quem o chamado pertence.
EDITAVEIS: tuple[str, ...] = ("summary", "severity")

#: As severidades que `create_ticket` reconhece. Ele COAGE silenciosamente o que não conhece
#: para "medium"; aqui a recusa é explícita, porque o número que o aprovador viu no formulário
#: tem que ser o que foi gravado.
SEVERIDADES: tuple[str, ...] = ("low", "medium", "high")

#: A chave da pergunta dentro de `input_requests`. É atribuída pelo servidor (o protocolo diz
#: "server-assigned") e volta como chave de `input_responses` — é por ela que a resposta é
#: encontrada na segunda rodada.
CHAVE_DA_PERGUNTA = "decisao"

#: A MARCA do estado entre as rodadas. Vai em `request_state`, o SDK a sela, e na volta ela tem
#: que bater exatamente. Não carrega dado nenhum da chamada de propósito: o resumo, a severidade
#: e o domínio já viajam nos argumentos da tool, que o próprio selo amarra por digest — repetir
#: qualquer um deles aqui criaria uma segunda cópia que poderia divergir da primeira.
MARCA_DO_ESTADO = "open_ticket/v1"

#: Empurrado pela composition root, como em `tools_knowledge.set_domain_registry`: os ids de
#: domínio que existem. Vem do catálogo (`DOMAIN_KINDS`), nunca de um literal aqui — uma segunda
#: lista faria a tool recusar um domínio que passou a existir, ou aceitar um que saiu.
_domain_ids: tuple[str, ...] = ()


def set_domain_ids(ids: tuple[str, ...]) -> None:
    """Recebe da composition root quais domínios podem receber um chamado.

    TODOS eles, não só os `grounded`: `helpdesk` não tem base de conhecimento e é justamente o
    que mais abre chamado. Quem filtra por tipo é a busca, não a escrita.
    """
    global _domain_ids
    _domain_ids = tuple(ids)


def _pergunta(pedido: ApprovalRequest) -> mcp_types.InputRequiredResult:
    """A pergunta ao aprovador — as quatro decisões no schema, não um sim/não.

    `requested_schema` é um subconjunto restrito de JSON Schema (só propriedades de primeiro
    nível, sem aninhamento), e é exatamente onde o vocabulário da ADR-019 cabe: um `enum` de
    quatro valores mais os dois campos que cada decisão usa. Um cliente que renderize o
    formulário mostra as quatro opções ao humano; um cliente que não renderize continua vendo
    o `enum` no schema e sabe o que pode responder.
    """
    args = pedido.args
    return mcp_types.InputRequiredResult(
        input_requests={
            CHAVE_DA_PERGUNTA: mcp_types.ElicitRequest(
                params=mcp_types.ElicitRequestFormParams(
                    message=(
                        f"Abrir chamado em '{args['domain']}' com severidade "
                        f"'{args['severity']}'?\n\n{args['summary']}\n\n"
                        "approve = abrir como está · edit = abrir com a sua correção "
                        "(`summary`/`severity`) · reject = não abrir (diga por quê em "
                        "`message`) · respond = não abrir, responda você mesmo em `message`. "
                        f"Exige o papel {' ou '.join(pedido.required_role)}."
                    ),
                    requested_schema={
                        "type": "object",
                        "properties": {
                            "decision": {
                                "type": "string",
                                "enum": list(pedido.allowed_decisions),
                                "description": "A decisão. As quatro da ADR-019.",
                            },
                            "summary": {
                                "type": "string",
                                "description": "Só em `edit`: o resumo corrigido.",
                            },
                            "severity": {
                                "type": "string",
                                "enum": list(SEVERIDADES),
                                "description": "Só em `edit`: a severidade corrigida.",
                            },
                            "message": {
                                "type": "string",
                                "description": "Em `reject`, o motivo; em `respond`, a resposta.",
                            },
                        },
                        "required": ["decision"],
                    },
                )
            )
        },
        request_state=MARCA_DO_ESTADO,
    )


def _ler_decisao(respostas: Any) -> tuple[str, dict, str]:
    """Da resposta do protocolo para `(tipo, args, mensagem)` do vocabulário da ADR-019.

    FECHA PARA O LADO DE NÃO ESCREVER, sempre — é o mesmo `_read_answer` da escalação do
    helpdesk, e pelo mesmo motivo: um payload malformado nunca pode ser o motivo de um chamado
    abrir. `decline` e `cancel` do protocolo viram `reject` (as duas são paradas, e parar é
    sempre permitido); uma decisão que o `enum` não previu também.
    """
    resposta = (respostas or {}).get(CHAVE_DA_PERGUNTA)
    acao = getattr(resposta, "action", None)
    conteudo = getattr(resposta, "content", None) or {}
    if acao != "accept":
        # `decline` = recusou explicitamente; `cancel` = dispensou sem decidir. As duas param, e
        # a diferença fica na mensagem para o modelo não tratá-las como a mesma coisa.
        motivo = "recusado pelo aprovador" if acao == "decline" else "dispensado sem decisão"
        return "reject", {}, motivo

    tipo = str(conteudo.get("decision", "")).lower()
    if tipo not in DECISOES:
        return "reject", {}, f"decisão não reconhecida: {tipo!r}"

    # Só os campos editáveis, e só quando vierem preenchidos. Um `edit` que sobrar vazio depois
    # deste filtro é recusado por `decide` — "um edit que não muda nada é uma aprovação, e tem
    # que ser mandado como uma".
    args = {c: conteudo[c] for c in EDITAVEIS if conteudo.get(c)} if tipo == "edit" else {}
    return tipo, args, str(conteudo.get("message", ""))


async def open_ticket(
    domain: str, summary: str, severity: str = "medium"
) -> dict | mcp_types.InputRequiredResult:
    """Abre um chamado — depois que um aprovador decidir, e nunca antes.

    A anotação de retorno declara as DUAS rodadas, e é assim que o FastMCP as reconhece: o arm
    `InputRequiredResult` é um sinal de suspensão, não dado de saída, então ele o remove do
    schema publicado e embrulha o retorno num `InputRequiredToolResult`
    (`fastmcp/tools/function_parsing.py`). O cliente continua vendo `dict` como saída da tool.
    """
    if not _domain_ids:
        raise RuntimeError(
            "catálogo de domínios não registrado — a composition root não chamou set_domain_ids"
        )

    # ANTES DE PERGUNTAR, e não depois: sem a chave que sela o estado, a resposta do aprovador
    # não voltaria verificável, e gastar a atenção de um humano para recusar na volta é pior do
    # que dizer de cara que a escrita está indisponível. Ver `mcp_app.request_state`.
    motivo = request_state.indisponivel()
    if motivo:
        raise ToolError(motivo)

    if domain not in _domain_ids:
        raise ToolError(
            f"domínio desconhecido: {domain!r} — válidos: {', '.join(_domain_ids)}"
        )
    if severity not in SEVERIDADES:
        raise ToolError(
            f"severidade inválida: {severity!r} — válidas: {', '.join(SEVERIDADES)}"
        )

    # Falha fechada com a auth ligada, e DECLARA o chamador: é dele que `hitl.decide` lê o papel
    # (`shared.auth.has_role`) e a trilha lê o ator (`audit.actor()`). Sem esta linha a decisão
    # seria autorizada contra ninguém e gravada como `process:app`.
    chamador = identidade_do_chamador(
        get_access_token(), erro="escrita sem identidade do chamador: envie o token do Entra"
    )

    # Modo shared: resolver o tenant E cobrar o entitlement, juntos (ADR-010). Abrir chamado num
    # domínio que o tenant não licenciou é escrever onde ele não deveria nem ler.
    recusa = recusa_de_tenant(chamador, domain)
    if recusa:
        raise ToolError(recusa)

    pedido = ApprovalRequest(
        action="create_ticket",
        args={"summary": summary, "severity": severity, "domain": domain},
        required_role=("Approver", "Admin"),
        allowed_decisions=DECISOES,
    )

    ctx = get_context()
    # AS DUAS CONDIÇÕES JUNTAS. Faltando qualquer uma, a pergunta é feita (de novo): respostas
    # sem estado significam que o cliente pulou a pergunta, e é exatamente o que não pode virar
    # escrita. O estado chega aqui já em texto puro — o `RequestStateBoundary` dessela antes, e
    # recusa no fio o que não foi este servidor que emitiu.
    if not ctx.input_responses or ctx.request_state != MARCA_DO_ESTADO:
        return _pergunta(pedido)

    tipo, args, mensagem = _ler_decisao(ctx.input_responses)
    # A severidade CORRIGIDA passa pela mesma régua da proposta, e ANTES de `decide` — depois
    # dele a decisão já estaria na trilha, e um evento de aprovação sem a escrita ao lado é uma
    # trilha que conta uma história que não aconteceu. Sem esta linha, `create_ticket` coagiria
    # em silêncio para "medium" o que o aprovador escreveu, e a trilha diria que ele corrigiu a
    # severidade para um valor que não foi gravado.
    if args.get("severity") and args["severity"] not in SEVERIDADES:
        raise ToolError(
            f"severidade corrigida inválida: {args['severity']!r} — "
            f"válidas: {', '.join(SEVERIDADES)}. Nenhum chamado foi aberto."
        )
    try:
        decisao = decide(pedido, tipo, args=args, message=mensagem)
    except NotAuthorized as recusada:
        # O texto fala do PAPEL, nunca de quem decidiu: a identidade do aprovador é da trilha,
        # não de uma mensagem que volta para o modelo do cliente (I-10).
        raise ToolError(f"decisão recusada: {recusada}. Nenhum chamado foi aberto.") from None

    if decisao.type in ("reject", "respond"):
        return {"decision": decisao.type, "ticket": None, "message": decisao.message}

    # O contrato de `ApprovalDecision.audit`: vazio significa que a decisão não ficou registrada,
    # e uma aprovação sem rastro não sustenta a regra 5. `decide` já falha fechado nesse caso —
    # esta linha é o lado do consumidor do mesmo contrato, e o que impede a próxima refatoração
    # de `_registrar` de virar uma escrita sem trilha em silêncio.
    if not decisao.audit:
        raise ToolError("decisão não registrada na trilha — nenhum chamado foi aberto.")

    # `edit` manda os valores do APROVADOR; `approve` mantém os que chegaram na chamada.
    final = {**pedido.args, **decisao.args}
    bilhete = create_ticket(final["summary"], final["severity"], domain=domain)
    return {"decision": decisao.type, "ticket": bilhete, "message": ""}


def register(mcp: FastMCP) -> None:
    """Registra a escrita. Exige que a composition root já tenha empurrado o catálogo.

    O `auth=` é `Approver`/`Admin` e não o conjunto de leitura: aqui o chamador é quem PROPÕE e
    quem DECIDE na mesma sessão, então quem não pode decidir não tem o que fazer com esta tool.
    Um Reader não a vê no `tools/list` — e uma chamada direta é recusada pelo mesmo gate.
    """
    if not _domain_ids:
        raise RuntimeError("set_domain_ids precisa rodar antes de registrar a escrita do MCP")
    mcp.tool(
        open_ticket,
        name="open_ticket",
        description=(
            # A lista vem do catálogo, como a de `search_docs`. E a descrição DIZ que há uma
            # rodada de decisão: um cliente que chame esperando resposta imediata e receba uma
            # pergunta não deve descobrir isso por tentativa.
            f"Abre um chamado em um domínio ({', '.join(_domain_ids)}). ESCRITA COM APROVAÇÃO: "
            "a primeira chamada devolve uma pergunta ao aprovador com quatro decisões "
            f"({', '.join(DECISOES)}); o chamado só é criado quando a chamada é repetida com a "
            "decisão. Exige o papel Approver ou Admin."
        ),
        tags={"tickets", "write"},
        auth=require_any_role("Approver", "Admin"),
    )
