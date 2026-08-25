"""UM `requestState`, UMA ESCRITA — o ataque do replay, medido antes e depois.

O `requestState` do protocolo é *verificável*, não é *de uso único*. O envelope do SDK amarra
método, tool, argumentos, principal e TTL (`mcp/server/request_state.py:364-407`) e não carrega
nada por rodada para consumir. Enquanto a marca do estado foi um literal fixo, a consequência era
esta, medida contra o servidor de verdade:

    o aprovador decide UMA vez → o cliente repete `tools/call` com o mesmo `requestState` e as
    mesmas `input_responses` → o segundo e o terceiro chamados são criados, inclusive de sessão
    nova, dentro dos 600s de TTL. A trilha grava 2 `approval` + 2 `write`, indistinguíveis de
    duas decisões humanas.

Não é escalação de privilégio — papel e principal seguram. É a quebra do invariante que a fase
existe para estabelecer, e faz a trilha da ADR-023 afirmar algo que não aconteceu. Um retry banal
de cliente LLM basta; não precisa de má-fé.

ESTE GATE CARREGA AS DUAS METADES DA PROVA, e é isso que o torna difícil de rebaixar: ele roda o
MESMO ataque contra um servidor com a reserva NEUTRALIZADA (o "antes": N chamados) e contra o
servidor de verdade (o "depois": 1 chamado). Uma asserção que só olhasse o depois ficaria verde
no dia em que a reserva virasse no-op.

    1. ANTES/DEPOIS   sem a reserva, três chamados de uma decisão; com ela, um.
    2. A RECUSA FALA  a mensagem do replay é DISTINTA de "estado inválido ou expirado" — as duas
                      pedem coisas opostas ao chamador.
    3. VIRA RASTRO    cada tentativa recusada entra na trilha como `replay`, e nenhuma entra
                      como `approval` ou `write`.
    4. NÃO É MEMÓRIA  a reserva é recusada até por um PROCESSO NOVO, que é o que a torna válida
                      com `minReplicas: 0` (a réplica morre entre a pergunta e a resposta) e com
                      mais de uma réplica (memória de processo não é compartilhada).
    5. NO LUGAR CERTO as reservas moram no mesmo diretório que `tickets.jsonl` — o mount do
                      Azure Files —, e não num caminho paralelo que só existe em disco efêmero.

OFFLINE COMO OS DEMAIS: o servidor é o que `build_app()` monta, servido por
`httpx2.ASGITransport` (pilha HTTP inteira, em processo, sem socket, sem daemon, sem rede); o
verificador de token é o estático de `tests.write_decision_test` (reusado, nunca copiado); os
chamados e as reservas vão para um diretório temporário; a chave do `requestState` é gerada na
hora. O subprocesso do item 4 roda o MESMO interpretador, sem rede.

    uv run python -m tests.decision_replay_test
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

import mcp_types
from fastmcp import Client
from fastmcp.client.transports.http import StreamableHttpTransport

import mcp_app
from app.modules.audit import public as audit
from app.modules.tickets.internal import tickets as store
from app.shared import auth as shared_auth
from app.shared.settings import settings
from mcp_app import decision_claim, tools_knowledge
from mcp_app import main as mcp_main
from mcp_app.auth import MCP_PATH
from mcp_app.tools_tickets import CHAVE_DA_PERGUNTA, MOTIVO_REPLAY
from tests.write_decision_test import (
    BASE,
    CLIENT_ID,
    PROPOSTA,
    TENANT,
    _auth_estatico,
    _fabrica,
)

#: O que o cliente repete. É o mesmo objeto nas três chamadas de propósito: o ataque não precisa
#: variar nada — precisa exatamente NÃO variar.
RESPOSTA = mcp_types.ElicitResult(action="accept", content={"decision": "approve"})


def _cliente(app, token: str = "tok-approver") -> Client:
    return Client(
        StreamableHttpTransport(url=BASE + MCP_PATH, auth=token, httpx_client_factory=_fabrica(app))
    )


async def _ataque(app, chamados) -> dict:
    """O ataque do revisor, na íntegra: decidir uma vez, repetir, e repetir de sessão NOVA."""
    antes = len(chamados())
    antes_trilha = len(audit.read("approvals"))
    tentativas: list[str] = []

    async with app.router.lifespan_context(app):
        async with _cliente(app) as c:
            pergunta = await c.session.call_tool(
                name="open_ticket", arguments=PROPOSTA, allow_input_required=True
            )
            selado = pergunta.request_state
            # DUAS chamadas na MESMA sessão, com o mesmo estado e a mesma resposta.
            for _ in range(2):
                tentativas.append(await _repete(c, selado))
        # E uma TERCEIRA de sessão nova — a que mostra que a defesa não pode ser da sessão.
        async with _cliente(app) as c:
            tentativas.append(await _repete(c, selado))

    novos = audit.read("approvals")[antes_trilha:]
    return {
        "tentativas": tentativas,
        "chamados": len(chamados()) - antes,
        "trilha": [e["kind"] for e in novos],
        "eventos": novos,
    }


async def _repete(cliente, estado: str) -> str:
    try:
        saida = await cliente.session.call_tool(
            name="open_ticket",
            arguments=PROPOSTA,
            input_responses={CHAVE_DA_PERGUNTA: RESPOSTA},
            request_state=estado,
            allow_input_required=True,
        )
    except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
        return f"RECUSADO {exc}"
    # `session.call_tool` é a camada CRUA do protocolo: uma `ToolError` do servidor volta como
    # resultado com `isError`, não como exceção (é o `call_tool` de alto nível do `Client` que
    # levanta). O ataque usa a camada crua porque precisa mandar `requestState` à mão — então a
    # recusa também precisa ser lida à mão.
    if getattr(saida, "is_error", False):
        texto = " ".join(getattr(bloco, "text", "") for bloco in (saida.content or []))
        return f"RECUSADO {texto.strip()}"
    corpo = getattr(saida, "structured_content", None) or {}
    bilhete = (corpo or {}).get("ticket") or {}
    return f"CRIOU {bilhete.get('id')}"


def _outro_processo(diretorio: Path, nonce: str) -> str:
    """`consumir` chamado de um PROCESSO NOVO, sobre o mesmo diretório de reservas.

    É a prova que memória não daria: se a reserva vivesse no processo, este subprocesso não
    saberia de nada e diria `True`. Um processo novo sobre o mesmo diretório é o modelo exato das
    duas hostilidades do ambiente — a réplica que morreu por ociosidade e voltou (`minReplicas:
    0`) e a segunda réplica que nunca viu a primeira.
    """
    programa = (
        "import pathlib,sys;"
        "from mcp_app import decision_claim as d;"
        "d.DIRETORIO=pathlib.Path(sys.argv[1]);"
        "print(d.consumir(sys.argv[2]))"
    )
    saida = subprocess.run(
        [sys.executable, "-c", programa, str(diretorio), nonce],
        capture_output=True,
        text=True,
        cwd=Path(mcp_app.__file__).resolve().parent.parent,
        check=False,
    )
    return (saida.stdout.strip().splitlines() or [saida.stderr.strip()[-200:]])[-1]


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
        decision_claim.consumir,
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.mcp_public_base_url,
        settings.mcp_request_state_key,
    )
    temporario = tempfile.TemporaryDirectory()

    async def retrieve_falso(_query, _user, _domain, *, top=8):
        return []

    def chamados() -> list[dict]:
        caminho = store._STORE
        if not caminho.exists():
            return []
        return [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]

    try:
        settings.entra_tenant_id = TENANT
        settings.entra_api_client_id = CLIENT_ID
        settings.mcp_public_base_url = BASE
        settings.mcp_request_state_key = secrets.token_hex(32)
        mcp_main.build_auth = _auth_estatico
        tools_knowledge.retrieve = retrieve_falso
        store._STORE = Path(temporario.name) / "tickets.jsonl"
        reservas = Path(temporario.name) / "decisoes"
        decision_claim.DIRETORIO = reservas

        # ── 1 · ANTES: a reserva NEUTRALIZADA, que é o servidor de antes deste conserto ──
        consumir_real = decision_claim.consumir
        decision_claim.consumir = lambda _nonce: True
        antes = asyncio.run(_ataque(mcp_main.build_app(), chamados))
        decision_claim.consumir = consumir_real

        print("\n  ANTES (com a reserva neutralizada — o comportamento que o revisor mediu):")
        for i, t in enumerate(antes["tentativas"], 1):
            print(f"     tentativa {i} · {t}")
        print(f"     CHAMADOS   : {antes['chamados']}      TRILHA: {antes['trilha']}")

        # ── 2 · DEPOIS: o servidor de verdade ────────────────────────────────────────────
        depois = asyncio.run(_ataque(mcp_main.build_app(), chamados))
        print("\n  DEPOIS (a reserva valendo):")
        for i, t in enumerate(depois["tentativas"], 1):
            print(f"     tentativa {i} · {t[:96]}")
        print(f"     CHAMADOS   : {depois['chamados']}      TRILHA: {depois['trilha']}\n")

        check(
            f"ANTES · uma decisão humana criava {antes['chamados']} chamados "
            f"(o ataque funciona, e é o que dá sentido ao resto)",
            antes["chamados"] == 3 and antes["trilha"] == ["approval", "write"] * 3,
        )
        check(
            f"DEPOIS · a MESMA decisão cria UM chamado ({depois['chamados']})",
            depois["chamados"] == 1,
        )
        check(
            "DEPOIS · a primeira tentativa cria; a segunda e a terceira são recusadas",
            depois["tentativas"][0].startswith("CRIOU")
            and all(t.startswith("RECUSADO") for t in depois["tentativas"][1:]),
        )
        check(
            "DEPOIS · e a terceira é de SESSÃO NOVA — a defesa não é da sessão",
            depois["tentativas"][2].startswith("RECUSADO"),
        )

        # ── 3 · a recusa DIZ o que é, e não se confunde com estado inválido ─────────────
        segunda = depois["tentativas"][1]
        check(
            f"a recusa fala de replay, não de estado inválido/expirado ({segunda[9:76]}…)",
            MOTIVO_REPLAY[:40] in segunda
            and "Invalid or expired requestState" not in segunda,
        )

        # ── 4 · a tentativa vira RASTRO ────────────────────────────────────────────────
        check(
            f"a trilha grava UMA decisão, UMA escrita e DUAS recusas ({depois['trilha']})",
            depois["trilha"] == ["approval", "write", "replay", "replay"],
        )
        replays = [e for e in depois["eventos"] if e["kind"] == "replay"]
        check(
            f"o evento de replay nomeia a decisão por DIGEST, nunca o nonce em claro "
            f"({replays[0]['ref']})",
            replays[0]["ref"].startswith("decisao:")
            and len(replays[0]["ref"]) == len("decisao:") + 16,
        )
        check(
            f"e grava o ator que tentou, não `process:app` ({replays[0]['actor']})",
            replays[0]["actor"].startswith("human:"),
        )

        # ── 5 · não é memória de processo ──────────────────────────────────────────────
        nonce = decision_claim.novo()
        primeiro = decision_claim.consumir(nonce)
        de_fora = _outro_processo(reservas, nonce)
        virgem = decision_claim.novo()
        de_fora_virgem = _outro_processo(reservas, virgem)
        print(f"     PROCESSO NOVO : reservado aqui → lá diz {de_fora} · nunca reservado → "
              f"lá diz {de_fora_virgem}")
        check(
            "uma reserva tomada NESTE processo é recusada em OUTRO — sobrevive a réplica e a "
            f"scale-to-zero ({primeiro} aqui, {de_fora} lá)",
            primeiro is True and de_fora == "False",
        )
        check(
            f"e um nonce nunca visto é aceito lá (a recusa é da reserva, não do subprocesso) "
            f"({de_fora_virgem})",
            de_fora_virgem == "True",
        )

        # ── 6 · no diretório certo ─────────────────────────────────────────────────────
        # Os dois caminhos são calculados separadamente (um em `tickets.py`, outro em
        # `decision_claim.py`) e PRECISAM apontar para o mesmo mount: uma reserva em disco
        # efêmero morreria no scale-to-zero e o replay voltaria, sem erro nenhum.
        real_reservas = original[3]
        real_chamados = original[2]
        check(
            f"as reservas moram ao lado de `tickets.jsonl`, no mount ({real_reservas})",
            real_reservas.parent == real_chamados.parent,
        )
    finally:
        (
            mcp_main.build_auth,
            tools_knowledge.retrieve,
            store._STORE,
            decision_claim.DIRETORIO,
            decision_claim.consumir,
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
    print("\n✅ um `requestState`, uma escrita — repetir o estado não abre um segundo chamado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
