"""A ESCRITA ATRAVESSA, e o contrato de decisão não se rebaixa — provado no fio, quatro vezes.

Este é o gate da fase que a spec chama de "maior superfície de risco": até aqui o servidor MCP
só lia. Ele responde a cinco perguntas, e responde MEDINDO contra um `fastmcp.Client` de
verdade — nada aqui é simulado a não ser as três coisas que têm que ser (o verificador de token,
o arquivo de chamados, e o `retrieve` da tool de leitura):

    1. AS QUATRO DECISÕES   aprovar · editar · rejeitar · responder atravessam INTEIRAS. `edit`
                            cria o chamado com a correção do APROVADOR, não com o texto que
                            chegou na chamada — é a decisão que motivou a ADR-019 e a que um
                            booleano não expressa.
    2. INALCANÇÁVEL         não há caminho até `create_ticket` que não passe pela decisão. Nem
                            chamando a tool direto, nem mandando respostas sem estado, nem
                            forjando o estado.
    3. O PAPEL É COBRADO    duas vezes, e as duas são medidas: quem não tem Approver/Admin não vê
                            a tool; e com o `auth=` REMOVIDO por mutação, `hitl.decide` continua
                            recusando — a segunda linha existe justamente para o dia em que
                            alguém esquecer a primeira.
    4. A TRILHA REGISTRA    dois eventos por escrita aprovada (a decisão e a escrita), com o ator
                            certo — o chamador, nunca `process:app` (ADR-023).
    5. O SELO ALCANÇA       a resposta FINAL é carimbada e carrega os dois eventos da trilha; a
                            rodada da PERGUNTA não é carimbada, porque não é uma resposta.
    6. O ESTADO É DE UM     o `requestState` emitido para um principal não serve para outro —
                            nem para um SEGUNDO aprovador, que tem o mesmo papel e só difere no
                            `sub`. É a propriedade que `mcp_app/request_state.py:12-15` chama de
                            a mais forte do módulo, e que nenhum gate media: os tokens daqui não
                            tinham `sub`, então todos degradavam para o mesmo principal e a
                            amarração nunca era exercitada. Provada por MUTAÇÃO, com
                            `bind_principal` removido.

O QUE ESTE GATE NÃO COBRE, e mora ao lado: o REPLAY — a mesma decisão apresentada duas vezes.
Está em `tests/decision_replay_test.py`, que é onde a reserva do nonce é medida antes e depois.

E mais duas, sobre o segredo novo (ADR-005): sem `MCP_REQUEST_STATE_KEY` a escrita se declara
indisponível **e a leitura continua funcionando**; com uma chave curta demais o app **não sobe**.

COMO ISTO CABE NUM GATE OFFLINE. Mesmo arranjo de `tests/client_surface_test.py` e
`tests/assurance_seal_test.py`: o servidor é o que `build_app()` monta — a MESMA fábrica que o
`uvicorn` sobe —, servido por `httpx2.ASGITransport` (pilha HTTP inteira, em processo, sem
socket, sem daemon e sem rede). A chave do `request_state` é GERADA AQUI, a cada execução: um
valor de exemplo que funcionasse, commitado, seria um segredo vazado mesmo valendo só em teste.
A TRILHA é a real — sem `AZURE_STORAGE_ACCOUNT` ela cai no `InMemoryTrail`, que encadeia por
hash igual à de produção.

    uv run python -m tests.write_decision_test
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sys
import tempfile
from pathlib import Path

import httpx2
import mcp_types
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.client.transports.http import StreamableHttpTransport
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from mcp.client.extension import advertise

from app.modules.audit import public as audit
from app.modules.tickets.internal import tickets as store
from app.shared import auth as shared_auth
from app.shared.settings import ENTRA_API_SCOPE_NAME, settings
from mcp_app import decision_claim, tools_knowledge, tools_tickets
from mcp_app import main as mcp_main
from mcp_app.assurance_extension import CHAVE_DO_SELO, IDENTIFICADOR
from mcp_app.auth import MCP_PATH
from mcp_app.request_state import MOTIVO_SEM_CHAVE
from mcp_app.tools_tickets import CHAVE_DA_PERGUNTA, MARCA_DO_ESTADO

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
BASE = "http://testserver"

#: O que a CHAMADA propõe. O `edit` corrige os dois campos, e é a diferença entre estes valores e
#: os de `CORRECAO` que prova que o chamado gravado é o do aprovador.
PROPOSTA = {"domain": "helpdesk", "summary": "pod em crashloop", "severity": "medium"}
CORRECAO = {"summary": "Kubernetes pod em CrashLoopBackOff", "severity": "high"}

APROVADOR = "aprovador@exemplo.invalid"

#: AS QUATRO DECISÕES DA ADR-019, ESCRITAS AQUI COMO LITERAL — e é por isso que este gate
#: consegue reprovar um rebaixamento.
#:
#: Enquanto a verificação comparava com `tools_tickets.DECISOES`, ela era tautológica: reduzir a
#: constante do servidor a `("approve", "reject")` fazia o check imprimir ✅ com
#: `['approve', 'reject']` — a única verificação nomeada pelo contrato-que-não-se-rebaixa não
#: conseguia reprovar o rebaixamento (o gate só ficava vermelho depois, por `TypeError` ao ler o
#: resultado do `edit`: um crash, não uma asserção). Um teste que lê a resposta do código não
#: testa o contrato, testa o eco.
#:
#: ESTA LISTA ESPELHA A ADR-019. Mudá-la exige mudar a ADR primeiro — não o contrário. Se um dia
#: o produto tiver uma quinta decisão, ela nasce lá e desce para cá.
DECISOES_DA_ADR = ["approve", "edit", "reject", "respond"]

#: TRÊS TOKENS, E OS TRÊS COM `sub` — que é o que faz deles TRÊS PRINCIPAIS.
#:
#: Sem `sub`, `principal_components` (`mcp/server/auth/provider.py:62-70`) degrada para
#: `(client_id, issuer, None)`: como os três compartilham o mesmo `client_id` e o verificador
#: estático não põe `iss`, os três viravam O MESMO principal — e a amarração por principal do
#: `requestState`, que `mcp_app/request_state.py:12-15` chama de a propriedade mais forte do
#: módulo ("o estado de uma aprovação não pode ser reaproveitado por outra pessoa"), não era
#: medida por gate nenhum. Medido: sem `sub`, o estado do aprovador era aceito no token do
#: leitor; com `sub`, é recusado.
#:
#: O SEGUNDO APROVADOR existe porque é ele quem isola a propriedade. O Reader também é recusado,
#: mas pelo `auth=` da tool — o papel para antes do principal. Só um segundo aprovador (mesmo
#: papel, `sub` diferente) chega ao ponto em que a ÚNICA coisa que pode recusá-lo é a amarração.
TOKENS = {
    "tok-approver": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": ["Approver"],
        "sub": "00000000-0000-0000-0000-0000000000cc",
        "oid": "00000000-0000-0000-0000-0000000000cc",
        "preferred_username": APROVADOR,
    },
    "tok-approver-2": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": ["Approver"],
        "sub": "00000000-0000-0000-0000-0000000000dd",
        "oid": "00000000-0000-0000-0000-0000000000dd",
        "preferred_username": "outro-aprovador@exemplo.invalid",
    },
    "tok-reader": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": ["Reader"],
        "sub": "00000000-0000-0000-0000-0000000000aa",
        "oid": "00000000-0000-0000-0000-0000000000aa",
        "preferred_username": "leitor@exemplo.invalid",
    },
}

LINHAS = [{"index": 1, "source": "page-11.md", "url": "https://conta/c/page-11.md", "snippet": "um"}]


def _auth_estatico(_base_url: str):
    """O provider que substitui `build_auth` — mesma classe, mesmo middleware, verificador
    estático no lugar do `AzureJWTVerifier` (que buscaria o JWKS do Entra pela rede)."""
    return RemoteAuthProvider(
        token_verifier=StaticTokenVerifier(TOKENS),
        authorization_servers=[f"https://login.microsoftonline.com/{TENANT}/v2.0"],
        base_url=BASE,
        resource_name="Foundry Assured MCP",
    )


def _fabrica(app):
    def fabrica(**kwargs):
        kwargs.pop("verify", None)
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE, **kwargs
        )

    return fabrica


def _cliente(app, token: str, *, decisao=None, acao="accept", negocia=False) -> Client:
    """Um `Client` de verdade. `decisao` é o que o "humano" responde ao formulário.

    O `elicitation_handler` é o lugar onde um cliente real mostraria as quatro opções a uma
    pessoa. Aqui ele devolve a decisão direto — o que está sob teste é o que o SERVIDOR faz com
    ela, não a interface que a coleta.
    """

    async def responde(_mensagem, _tipo, params, _contexto):
        # O schema chega ao cliente com as quatro decisões no `enum` — é a prova de que o
        # vocabulário viaja no protocolo em vez de ser reduzido no servidor.
        opcoes.append(params.requested_schema["properties"]["decision"]["enum"])
        return ElicitResult(action=acao, content=decisao)

    opcoes: list = []
    cliente = Client(
        StreamableHttpTransport(url=BASE + MCP_PATH, auth=token, httpx_client_factory=_fabrica(app)),
        elicitation_handler=responde,
        extensions=[advertise(IDENTIFICADOR)] if negocia else None,
    )
    cliente.opcoes_vistas = opcoes  # type: ignore[attr-defined]
    return cliente


def _ticket(resultado: dict) -> dict:
    """O chamado que uma rodada criou, ou `{}` quando ela foi recusada.

    Existe para que uma asserção vermelha não vire um crash: quando o corpo é `"RECUSADO …"`
    (uma string), indexar `["ticket"]["summary"]` levanta `TypeError` e leva o gate inteiro
    junto — o relatório para de imprimir e quem lê não vê qual verificação falhou.
    """
    corpo = resultado.get("corpo")
    if not isinstance(corpo, dict):
        return {}
    return corpo.get("ticket") or {}


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    logging.disable(logging.CRITICAL)

    original = (
        mcp_main.build_auth,
        tools_knowledge.retrieve,
        store._STORE,
        decision_claim.DIRETORIO,
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.mcp_public_base_url,
        settings.mcp_request_state_key,
    )
    temporario = tempfile.TemporaryDirectory()

    async def retrieve_falso(_query, _user, _domain, *, top=8):
        return list(LINHAS)

    def chamados() -> list[dict]:
        """Os chamados REALMENTE gravados por `create_ticket` — o arquivo, não um contador."""
        caminho = store._STORE
        if not caminho.exists():
            return []
        return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]

    try:
        settings.entra_tenant_id = TENANT
        settings.entra_api_client_id = CLIENT_ID
        settings.mcp_public_base_url = BASE
        # A CHAVE É GERADA AGORA — nunca lida do repositório. 32 bytes é o mínimo que o
        # `AESGCMRequestStateCodec` aceita, e o comando é o que a própria biblioteca sugere.
        settings.mcp_request_state_key = secrets.token_hex(32)
        mcp_main.build_auth = _auth_estatico
        tools_knowledge.retrieve = retrieve_falso
        store._STORE = Path(temporario.name) / "tickets.jsonl"
        # As RESERVAS de decisão vão para o mesmo diretório temporário — em produção elas moram
        # ao lado de `tickets.jsonl`, no share montado, e aqui o "share" é este tmpdir.
        decision_claim.DIRETORIO = Path(temporario.name) / "decisoes"

        app = mcp_main.build_app()

        async def decide_pelo_fio(token, decisao, acao="accept", *, negocia=False):
            async with _cliente(app, token, decisao=decisao, acao=acao, negocia=negocia) as c:
                r = await c.call_tool("open_ticket", PROPOSTA)
                return r, list(c.opcoes_vistas)  # type: ignore[attr-defined]

        async def roda():
            saida: dict = {}
            async with app.router.lifespan_context(app):
                # ── 1 · as quatro decisões, uma a uma ────────────────────────────────────
                for rotulo, conteudo in (
                    ("approve", {"decision": "approve"}),
                    ("edit", {"decision": "edit", **CORRECAO}),
                    ("reject", {"decision": "reject", "message": "já resolvido no runbook"}),
                    ("respond", {"decision": "respond", "message": "reinicie o deployment"}),
                    # Um `edit` cuja severidade corrigida não existe: recusado ANTES de `decide`,
                    # para não deixar na trilha uma aprovação sem a escrita ao lado.
                    ("edit_torto", {"decision": "edit", "severity": "catastrofica"}),
                ):
                    antes = len(chamados())
                    antes_trilha = len(audit.read("approvals"))
                    try:
                        r, opcoes = await decide_pelo_fio("tok-approver", conteudo, negocia=True)
                        corpo, selo = r.structured_content, (r.meta or {}).get(CHAVE_DO_SELO)
                    except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
                        corpo, selo, opcoes = f"RECUSADO {exc}", None, []
                    saida[rotulo] = {
                        "corpo": corpo,
                        "selo": selo,
                        "novos": len(chamados()) - antes,
                        "opcoes": opcoes,
                        "trilha": audit.read("approvals")[-2:],
                        "novos_na_trilha": len(audit.read("approvals")) - antes_trilha,
                    }

                # `decline` e `cancel` do protocolo: paradas, não escritas.
                for rotulo, acao in (("decline", "decline"), ("cancel", "cancel")):
                    antes = len(chamados())
                    r, _ = await decide_pelo_fio("tok-approver", None, acao)
                    saida[rotulo] = {"corpo": r.structured_content, "novos": len(chamados()) - antes}

                # ── 2 · inalcançável sem decisão ─────────────────────────────────────────
                antes = len(chamados())
                resposta_forjada = mcp_types.ElicitResult(
                    action="accept", content={"decision": "approve"}
                )
                async with Client(
                    StreamableHttpTransport(
                        url=BASE + MCP_PATH, auth="tok-approver", httpx_client_factory=_fabrica(app)
                    )
                ) as c:
                    saida["tools_do_aprovador"] = sorted(t.name for t in await c.list_tools())
                    # (a) a tool chamada DIRETO, sem cliente que responda formulário nenhum
                    direto = await c.session.call_tool(
                        name="open_ticket", arguments=PROPOSTA, allow_input_required=True
                    )
                    saida["direto"] = type(direto).__name__
                    saida["selo_da_pergunta"] = (getattr(direto, "meta", None) or {}).get(
                        CHAVE_DO_SELO
                    )
                    # (b) respostas SEM o estado — o cliente tentando pular a pergunta
                    sem_estado = await c.session.call_tool(
                        name="open_ticket",
                        arguments=PROPOSTA,
                        input_responses={CHAVE_DA_PERGUNTA: resposta_forjada},
                        allow_input_required=True,
                    )
                    saida["sem_estado"] = type(sem_estado).__name__
                    # (c) estado FORJADO e (d) estado em TEXTO PURO (a marca que o servidor usa
                    #     internamente, como se não houvesse selo nenhum)
                    for rotulo, estado in (
                        ("forjado", "v1." + "A" * 44),
                        ("texto_puro", MARCA_DO_ESTADO),
                    ):
                        try:
                            await c.session.call_tool(
                                name="open_ticket",
                                arguments=PROPOSTA,
                                input_responses={CHAVE_DA_PERGUNTA: resposta_forjada},
                                request_state=estado,
                                allow_input_required=True,
                            )
                            saida[rotulo] = "PASSOU"
                        except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
                            saida[rotulo] = f"RECUSADO {type(exc).__name__}: {exc}"
                saida["burla_criou"] = len(chamados()) - antes

                # ── 2b · o estado de UMA pessoa não serve para OUTRA ──────────────────────
                #
                # A propriedade mais forte do módulo do selo, e a que não era medida por gate
                # nenhum: `mcp/server/request_state.py` amarra o envelope ao PRINCIPAL
                # autenticado, então "o servidor perguntou a você" não vira "o servidor
                # perguntou a alguém".
                #
                # A pergunta é feita e NÃO é respondida de propósito: com o nonce ainda por
                # reservar, a única coisa capaz de recusar o segundo aprovador é a amarração
                # por principal. Se a resposta já tivesse sido dada, a reserva recusaria antes
                # e o teste passaria pelo motivo errado.
                antes = len(chamados())
                async with Client(
                    StreamableHttpTransport(
                        url=BASE + MCP_PATH, auth="tok-approver", httpx_client_factory=_fabrica(app)
                    )
                ) as c:
                    pergunta = await c.session.call_tool(
                        name="open_ticket", arguments=PROPOSTA, allow_input_required=True
                    )
                saida["reuso"] = {}
                for rotulo, token in (("aprovador_2", "tok-approver-2"), ("leitor", "tok-reader")):
                    saida["reuso"][rotulo] = await _reusa_estado(
                        app, token, pergunta.request_state, resposta_forjada
                    )
                saida["reuso_criou"] = len(chamados()) - antes

                # ── 3 · o papel é cobrado (primeira linha: a tool não existe) ─────────────
                antes = len(chamados())
                async with _cliente(app, "tok-reader", decisao={"decision": "approve"}) as c:
                    saida["tools_do_leitor"] = sorted(t.name for t in await c.list_tools())
                    try:
                        await c.call_tool("open_ticket", PROPOSTA)
                        saida["leitor"] = "PASSOU"
                    except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
                        saida["leitor"] = f"RECUSADO {type(exc).__name__}"
                saida["leitor_criou"] = len(chamados()) - antes
            return saida

        r = asyncio.run(roda())

        # ── 1 · as quatro decisões ──────────────────────────────────────────────────────
        gravados = chamados()
        print(f"     CHAMADOS   : {[t['summary'] for t in gravados]}")
        # CONTRA O CONTRATO, NÃO CONTRA O CÓDIGO. As duas metades importam: a de baixo prova que o
        # servidor não rebaixou a constante, a de cima prova que o vocabulário inteiro chegou ao
        # cliente. Comparar a segunda com `tools_tickets.DECISOES` faria as duas dizerem a mesma
        # coisa — e um rebaixamento passaria por ✅ nas duas.
        check(
            f"o contrato da ADR-019 tem QUATRO decisões, e é essa a constante do servidor "
            f"({list(tools_tickets.DECISOES)})",
            list(tools_tickets.DECISOES) == DECISOES_DA_ADR,
        )
        check(
            f"e as QUATRO chegam ao cliente no `enum` do formulário ({r['approve']['opcoes'][:1]})",
            r["approve"]["opcoes"] == [DECISOES_DA_ADR],
        )
        check(
            "approve · cria o chamado com o resumo proposto",
            r["approve"]["novos"] == 1
            and _ticket(r["approve"]).get("summary") == PROPOSTA["summary"],
        )
        # Leitura DEFENSIVA a partir daqui: sob a mutação que rebaixa `DECISOES`, o `edit` é
        # recusado e `corpo` vira uma string. Ler `corpo["ticket"]["summary"]` direto estouraria
        # com `TypeError` — o gate morreria de crash DEPOIS de a asserção certa já ter ficado
        # vermelha, e o relatório sairia truncado justamente na hora em que ele é mais lido.
        check(
            f"edit · cria o chamado com a CORREÇÃO do aprovador "
            f"({_ticket(r['edit']).get('summary')!r}, {_ticket(r['edit']).get('severity')!r})",
            r["edit"]["novos"] == 1
            and _ticket(r["edit"]).get("summary") == CORRECAO["summary"]
            and _ticket(r["edit"]).get("severity") == CORRECAO["severity"],
        )
        check(
            "edit · e o texto que a CHAMADA propôs não foi gravado em lugar nenhum",
            all(t["summary"] != PROPOSTA["summary"] for t in gravados[1:2]),
        )
        check(
            f"reject · não cria nada, e a recusa carrega o motivo ({r['reject']['corpo']['message']!r})",
            r["reject"]["novos"] == 0
            and r["reject"]["corpo"]["ticket"] is None
            and r["reject"]["corpo"]["message"] == "já resolvido no runbook",
        )
        check(
            f"respond · não cria nada, e a resposta do aprovador volta ({r['respond']['corpo']['message']!r})",
            r["respond"]["novos"] == 0
            and r["respond"]["corpo"]["ticket"] is None
            and r["respond"]["corpo"]["message"] == "reinicie o deployment",
        )
        check(
            f"edit com severidade inexistente é recusado ANTES de `decide` — nada escrito e "
            f"NADA na trilha ({str(r['edit_torto']['corpo'])[:52]}…)",
            str(r["edit_torto"]["corpo"]).startswith("RECUSADO")
            and r["edit_torto"]["novos"] == 0
            and r["edit_torto"]["novos_na_trilha"] == 0,
        )
        check(
            "decline e cancel do protocolo param a escrita (as duas viram `reject`)",
            r["decline"]["novos"] == 0
            and r["cancel"]["novos"] == 0
            and r["decline"]["corpo"]["decision"] == "reject"
            and r["cancel"]["corpo"]["decision"] == "reject",
        )

        # ── 2 · a escrita é inalcançável sem decisão ────────────────────────────────────
        # A LISTA É LITERAL, e é o inventário do que um Approver enxerga. O que ela afirma é
        # uma AUSÊNCIA: nenhuma segunda tool que crie chamado. `show_evidence` entrou na Fase 5
        # (a tabela de evidências) e é leitura pura — o gate `app_evidencias_test` prova que ela
        # só republica ao próprio chamador as citações que `search_docs` já devolveu.
        check(
            f"a única tool que escreve é `open_ticket` — o resto lê: {r['tools_do_aprovador']}",
            r["tools_do_aprovador"] == ["open_ticket", "search_docs", "show_evidence"],
        )
        check(
            f"chamada DIRETA devolve a pergunta, não um chamado ({r['direto']})",
            r["direto"] == "InputRequiredResult",
        )
        check(
            f"respostas SEM estado: o servidor pergunta de novo ({r['sem_estado']})",
            r["sem_estado"] == "InputRequiredResult",
        )
        for rotulo in ("forjado", "texto_puro"):
            check(
                f"estado {rotulo} é recusado NO FIO, antes do corpo rodar ({str(r[rotulo])[:60]})",
                str(r[rotulo]).startswith("RECUSADO"),
            )
        check(
            f"e nenhuma das quatro tentativas escreveu nada ({r['burla_criou']} chamados)",
            r["burla_criou"] == 0,
        )

        # ── 2b · o estado de uma pessoa não serve para outra ────────────────────────────
        reuso = r["reuso"]
        print(f"     REUSO      : aprovador_2 → {reuso['aprovador_2'][:58]}")
        check(
            f"um SEGUNDO aprovador (mesmo papel, `sub` diferente) NÃO usa o estado do primeiro "
            f"({reuso['aprovador_2'][:44]})",
            reuso["aprovador_2"].startswith("RECUSADO")
            and "Invalid or expired requestState" in reuso["aprovador_2"],
        )
        check(
            f"e o Reader tampouco ({reuso['leitor'][:44]})",
            reuso["leitor"].startswith("RECUSADO"),
        )
        check(
            f"nenhum dos dois reusos escreveu ({r['reuso_criou']} chamados)",
            r["reuso_criou"] == 0,
        )
        problema = asyncio.run(_mutacao_do_principal(chamados))
        check(
            "MUTAÇÃO · com `bind_principal` REMOVIDO, o segundo aprovador reusa o estado e "
            "ESCREVE — é o que dá dentes à verificação acima"
            + (f" — {problema}" if problema else ""),
            problema is None,
        )

        # ── 3 · o papel é cobrado, nas duas linhas ──────────────────────────────────────
        check(
            f"sem Approver/Admin a ESCRITA não existe — só as leituras ({r['tools_do_leitor']})",
            r["tools_do_leitor"] == ["search_docs", "show_evidence"],
        )
        check(
            f"e a chamada direta dele é recusada ({r['leitor']})",
            str(r["leitor"]).startswith("RECUSADO") and r["leitor_criou"] == 0,
        )
        problema = asyncio.run(_defesa_em_profundidade(chamados))
        check(
            "MUTAÇÃO · com o `auth=` REMOVIDO, `hitl.decide` ainda recusa o Reader"
            + (f" — {problema}" if problema else ""),
            problema is None,
        )
        problema = asyncio.run(_mutacao_do_gate_de_seguranca())
        check(
            "MUTAÇÃO · a escrita sem `auth=` é pega pela matriz de instrumentação"
            + (f" — {problema}" if problema else ""),
            problema is None,
        )

        # ── 4 · a trilha registra, com o ator certo ─────────────────────────────────────
        decisao_ev, escrita_ev = r["approve"]["trilha"]
        print(f"     TRILHA     : {decisao_ev['kind']}/{decisao_ev['summary']} · "
              f"{escrita_ev['kind']}/{escrita_ev['summary']}")
        check(
            "a DECISÃO entra na trilha (kind=approval), com o tipo e o papel do aprovador",
            decisao_ev["kind"] == "approval"
            and decisao_ev["detail"]["decision"] == "approve"
            and decisao_ev["detail"]["roles"] == ["Approver"],
        )
        check(
            f"a ESCRITA entra na trilha (kind=write), referenciando o chamado "
            f"({escrita_ev['ref']})",
            escrita_ev["kind"] == "write"
            and escrita_ev["ref"] == r["approve"]["corpo"]["ticket"]["id"],
        )
        check(
            f"e o ATOR dos dois é o chamador, não `process:app` ({decisao_ev['actor']})",
            APROVADOR in decisao_ev["actor"] and APROVADOR in escrita_ev["actor"],
        )
        campos = r["edit"]["trilha"][0]["detail"].get("edited_fields")
        check(
            f"no `edit`, a trilha grava QUE CAMPOS foram corrigidos — e não os valores ({campos})",
            campos == sorted(CORRECAO)
            and CORRECAO["summary"] not in json.dumps(r["edit"]["trilha"], ensure_ascii=False),
        )
        rejeicao = r["reject"]["trilha"][-1]
        check(
            "e um `reject` deixa rastro da decisão SEM nenhum evento de escrita ao lado",
            rejeicao["kind"] == "approval" and rejeicao["detail"]["decision"] == "reject",
        )

        # ── 5 · o selo alcança a escrita ────────────────────────────────────────────────
        selo = r["approve"]["selo"]
        print(f"     SELO       : {json.dumps(selo, ensure_ascii=False)}")
        check("a resposta FINAL da escrita é carimbada", selo is not None)
        check(
            f"o selo carrega os DOIS eventos da trilha ({[e['kind'] for e in (selo or {}).get('audit', [])]})",
            [e["kind"] for e in (selo or {}).get("audit", [])] == ["approval", "write"]
            and [e["id"] for e in selo["audit"]] == [decisao_ev["hash"], escrita_ev["hash"]],
        )
        check(
            "e NÃO carrega `citations`: esta tool não fundamenta nada, e um `[]` mentiria "
            "dizendo que tentou citar",
            "citations" not in (selo or {}),
        )
        check(
            "o selo não carrega o resumo do chamado nem quem aprovou",
            PROPOSTA["summary"] not in json.dumps(selo, ensure_ascii=False)
            and APROVADOR not in json.dumps(selo, ensure_ascii=False),
        )
        check(
            f"a rodada da PERGUNTA não é carimbada — não é uma resposta ({r['selo_da_pergunta']})",
            r["selo_da_pergunta"] is None,
        )

        # ── 6 · o segredo novo: ausente é indisponibilidade, curto é erro ───────────────
        sem_chave = asyncio.run(_sem_chave(chamados))
        check(
            f"SEM a chave, a escrita se declara indisponível ({str(sem_chave['escrita'])[:70]})",
            MOTIVO_SEM_CHAVE in str(sem_chave["escrita"]) and sem_chave["criou"] == 0,
        )
        check(
            "SEM a chave, a LEITURA continua funcionando (a indisponibilidade é só da escrita)",
            sem_chave["leitura"] == len(LINHAS),
        )
        check(
            f"e a escrita continua VISÍVEL, para o chamador saber que ela existe "
            f"({sem_chave['tools']})",
            sem_chave["tools"] == ["open_ticket", "search_docs", "show_evidence"],
        )
        check(
            f"chave PRESENTE porém curta: o app não sobe ({sem_chave['curta']})",
            "32 bytes" in str(sem_chave["curta"]),
        )
    finally:
        (
            mcp_main.build_auth,
            tools_knowledge.retrieve,
            store._STORE,
            decision_claim.DIRETORIO,
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.mcp_public_base_url,
            settings.mcp_request_state_key,
        ) = original
        shared_auth._current_user.set(None)
        temporario.cleanup()
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ as quatro decisões atravessam; sem decisão e sem papel, nada escreve.")
    return 0


async def _reusa_estado(app, token: str, estado: str, resposta) -> str:
    """Um token TENTA usar o `requestState` que o servidor emitiu para outro. O que volta."""
    async with Client(
        StreamableHttpTransport(url=BASE + MCP_PATH, auth=token, httpx_client_factory=_fabrica(app))
    ) as c:
        try:
            saida = await c.session.call_tool(
                name="open_ticket",
                arguments=PROPOSTA,
                input_responses={CHAVE_DA_PERGUNTA: resposta},
                request_state=estado,
                allow_input_required=True,
            )
        except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
            return f"RECUSADO {type(exc).__name__}: {exc}"
    # `session.call_tool` é a camada CRUA: uma `ToolError` do servidor (o gate de papel, por
    # exemplo) volta como resultado com `is_error`, não como exceção — só o `call_tool` de alto
    # nível levanta. Sem esta leitura, uma recusa do Reader seria relatada como "PASSOU".
    if getattr(saida, "is_error", False):
        texto = " ".join(getattr(bloco, "text", "") for bloco in (saida.content or []))
        return f"RECUSADO ToolError: {texto.strip()}"
    corpo = getattr(saida, "structured_content", None)
    return f"PASSOU {corpo}"


async def _mutacao_do_principal(chamados) -> str | None:
    """A amarração por principal REMOVIDA — e o segundo aprovador passa a escrever.

    Sem esta mutação, a verificação acima (o estado de um não serve para outro) poderia estar
    verde por qualquer outro motivo: um argumento que difere, um TTL, um erro de transporte. Aqui
    a política é reconstruída com `bind_principal=None` (o único ponto trocado, e é o mesmo
    parâmetro que `mcp/server/request_state.py:118-124` expõe) e o que se espera é o OPOSTO:
    o estado do primeiro aprovador aceito no token do segundo, com o chamado criado.

    Devolve `None` quando a mutação de fato afrouxou — isto é, quando a asserção normal tem
    dentes.
    """
    from mcp.server.request_state import RequestStateSecurity

    from mcp_app import request_state as rs

    original = rs.politica
    try:
        rs.politica = lambda: RequestStateSecurity(
            keys=[settings.mcp_request_state_key.strip()], bind_principal=None
        )
        app = mcp_main.build_app()
    finally:
        rs.politica = original

    resposta = mcp_types.ElicitResult(action="accept", content={"decision": "approve"})
    antes = len(chamados())
    async with app.router.lifespan_context(app):
        async with Client(
            StreamableHttpTransport(
                url=BASE + MCP_PATH, auth="tok-approver", httpx_client_factory=_fabrica(app)
            )
        ) as c:
            pergunta = await c.session.call_tool(
                name="open_ticket", arguments=PROPOSTA, allow_input_required=True
            )
        saida = await _reusa_estado(app, "tok-approver-2", pergunta.request_state, resposta)
    if not saida.startswith("PASSOU"):
        return f"a mutação não afrouxou nada — o reuso continuou recusado ({saida[:80]})"
    if len(chamados()) != antes + 1:
        return "a mutação passou mas não criou o chamado — o teste não mede o que diz medir"
    return None


async def _defesa_em_profundidade(chamados) -> str | None:
    """A SEGUNDA linha do gate de papel, medida com a primeira REMOVIDA.

    Pelo fio não há como alcançá-la: quem falha em `hitl.decide` é exatamente quem o `auth=` da
    tool já filtrou, então as duas linhas se sobrepõem — e é por isso que só a mutação prova que
    a de baixo existe. Aqui a tool é registrada SEM `auth=` (o defeito que a matriz de
    instrumentação pega) e um Reader chega ao corpo: `decide` recusa, e nada é escrito.

    A montagem é a real (`build_app`), com um único ponto trocado — `tools_tickets.register` —
    para que o resto do caminho (middleware de auth, `caller`, contextvar do usuário) seja o
    mesmo que roda em produção.
    """
    original = tools_tickets.register

    def registra_sem_dono(mcp):
        mcp.tool(tools_tickets.open_ticket, name="open_ticket", description="sem dono")

    try:
        tools_tickets.register = registra_sem_dono
        app = mcp_main.build_app()
    finally:
        tools_tickets.register = original

    antes = len(chamados())
    async with (
        app.router.lifespan_context(app),
        _cliente(app, "tok-reader", decisao={"decision": "approve"}) as c,
    ):
        visiveis = sorted(t.name for t in await c.list_tools())
        if "open_ticket" not in visiveis:
            return f"a mutação não expôs a tool ao Reader (visíveis: {visiveis})"
        try:
            await c.call_tool("open_ticket", PROPOSTA)
            return "o Reader ESCREVEU com o `auth=` removido — a segunda linha não existe"
        except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
            if "Approver" not in str(exc):
                return f"recusou, mas não pelo papel: {exc}"
    if len(chamados()) != antes:
        return "recusou e mesmo assim gravou um chamado"
    return None


async def _mutacao_do_gate_de_seguranca() -> str | None:
    """A escrita registrada SEM `auth=` tem que ficar VERMELHA na matriz de instrumentação.

    É a instrução que vem valendo nesta série — superfície nova entra na matriz no mesmo commit
    em que nasce — provada pelo lado que interessa: não que a linha existe no dicionário, mas que
    o mecanismo reprova quando ela nasce sem dono. Usa a MESMA função do gate
    (`instrumentation_matrix_test._sem_auth` sobre `_registro_cru`), não uma reimplementação.
    """
    from fastmcp import FastMCP

    from tests.instrumentation_matrix_test import _registro_cru, _sem_auth

    descartavel = FastMCP("mutação-da-escrita", tools=[])
    descartavel.tool(tools_tickets.open_ticket, name="open_ticket")  # sem `auth=`, de propósito
    achadas = _sem_auth(await _registro_cru(descartavel))
    if achadas != ["tool:open_ticket"]:
        return f"a matriz não pegou a escrita sem `auth=` — achadas={achadas!r}"
    return None


async def _sem_chave(chamados) -> dict:
    """O comportamento documentado quando o segredo novo não está configurado.

    Duas metades, e as duas importam: a escrita se recusa com motivo legível, e TUDO O MAIS
    continua de pé. Um servidor que morresse por falta de uma chave que só a escrita usa
    trocaria uma lacuna de configuração de escrita por indisponibilidade de leitura.
    """
    saida: dict = {}
    settings.mcp_request_state_key = ""
    app = mcp_main.build_app()
    antes = len(chamados())
    async with (
        app.router.lifespan_context(app),
        _cliente(app, "tok-approver", decisao={"decision": "approve"}) as c,
    ):
        saida["tools"] = sorted(t.name for t in await c.list_tools())
        try:
            await c.call_tool("open_ticket", PROPOSTA)
            saida["escrita"] = "PASSOU"
        except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
            saida["escrita"] = str(exc)
        leitura = await c.call_tool("search_docs", {"domain": "techdocs", "query": "x"})
        saida["leitura"] = len(leitura.structured_content["sources"])
    saida["criou"] = len(chamados()) - antes

    # E a chave curta: erro de operação, não modo suportado. O app não sobe.
    settings.mcp_request_state_key = "curta-demais"
    try:
        mcp_main.build_app()
        saida["curta"] = "SUBIU"
    except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
        saida["curta"] = str(exc)
    return saida


if __name__ == "__main__":
    sys.exit(main())
