"""O contextvar de identidade SOBREVIVE dentro do gerador do StreamingResponse.

POR QUE ISTO É GATE, E POR QUE ELE NASCE CONTRADIZENDO O CÓDIGO. Três lugares em
`grounded/internal/grounded.py` afirmam, com a palavra "verified", que `current_user()` se PERDE
dentro do gerador — e a afirmação é carga estrutural: ela é a razão declarada de o usuário ser
capturado no endpoint e passado adiante, e a razão de o mesmo ser feito com o idioma.

Medido hoje, contra **uvicorn de verdade** (não só TestClient) e com a mesma forma de montagem do
endpoint grounded (`add_api_route` + `async def` + `StreamingResponse`), o contextvar sobrevive: no
início do gerador e depois de um `await`. O achado original é de 2026-07-01 e o Starlette está em
1.3.1 — um major desde então. A causa da mudança não foi medida e não se afirma aqui; o que se
afirma é o presente.

O QUE ESTE GATE DECIDE. Não é curiosidade: se o contextvar NÃO sobrevivesse, ler a identidade
dentro do caminho de streaming devolveria `None` e cairia silenciosamente na identidade da
aplicação — que 403 na inferência crua e, no `retrieve`, deixaria de trimar por ACL. Ou seja: o
modo de falha é "serve documento demais", que é o pior tipo. Enquanto o contextvar sobrevive, o
`GroundedRetrieval` pode ler a identidade por conta e o caminho grounded pode virar agente comum do
framework. Se um dia parar de sobreviver, este teste falha ANTES de alguém apoiar um desenho nisso.

A captura explícita no endpoint NÃO é removida por causa deste resultado. Ela continua correta —
passar dado de requisição explicitamente é melhor desenho do que lê-lo de um contextvar — e é o
lado seguro para errar. O que muda é que ela deixa de ser uma obrigação imposta pelo runtime.
"""

from __future__ import annotations

import sys

# NO NÍVEL DO MÓDULO, e não dentro de `_app()`, de propósito: com `from __future__ import
# annotations` as anotações viram STRING, e o FastAPI as resolve pelo namespace do MÓDULO. Com o
# import local, `Request` não é encontrado, o parâmetro vira query param obrigatório e a rota
# responde 422 sem nunca chamar a função — a mesma família de falha que já mordeu a dependência de
# amarração, por outro caminho.
from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse

MARCA = "u-contextvar-probe"


def _app():
    """Um app com a MESMA forma do endpoint grounded: `add_api_route`, `async def`, streaming."""
    from app.shared import auth

    class _Usuario:
        oid = MARCA

        def __repr__(self) -> str:
            return f"User({MARCA})"

    async def _dependencia_que_seta() -> None:
        # É exatamente o que `require_user` faz quando a autenticação está ligada.
        auth._current_user.set(_Usuario())

    async def _endpoint(request: Request) -> StreamingResponse:
        capturado = auth.current_user()

        async def gerar():
            import asyncio

            yield f"capturado={getattr(capturado, 'oid', None)};"
            yield f"inicio={getattr(auth.current_user(), 'oid', None)};"
            # Depois de um await é o caso REAL: o stream do agente sempre suspende.
            await asyncio.sleep(0)
            yield f"pos_await={getattr(auth.current_user(), 'oid', None)};"

        return StreamingResponse(gerar(), media_type="text/plain")

    aplicacao = FastAPI()
    aplicacao.add_api_route(
        "/probe", _endpoint, methods=["POST"], dependencies=[Depends(_dependencia_que_seta)]
    )
    return aplicacao


def main() -> int:
    from fastapi.testclient import TestClient

    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    corpo = TestClient(_app()).post("/probe", json={}).text
    lido = dict(
        parte.split("=", 1) for parte in corpo.strip(";").split(";") if "=" in parte
    )

    check("o endpoint enxerga a identidade (a captura funciona)", lido.get("capturado") == MARCA)
    check(
        "…e ela SOBREVIVE dentro do gerador do StreamingResponse",
        lido.get("inicio") == MARCA,
    )
    check(
        "…inclusive depois de um await, que é o caso real do stream",
        lido.get("pos_await") == MARCA,
    )

    if falhas:
        print(
            "\n❌ o contextvar de identidade parou de atravessar o streaming.\n"
            "   CONSEQUÊNCIA: ler a identidade dentro do caminho de streaming passa a devolver\n"
            "   None e a cair na identidade da aplicação — que 403 na inferência crua e, no\n"
            "   `retrieve`, DEIXA DE TRIMAR POR ACL. O modo de falha é servir documento demais.\n"
            "   Capture a identidade no endpoint e passe adiante, como o caminho grounded já faz."
        )
        return 1
    print("\n✅ a identidade atravessa o StreamingResponse — capturar no endpoint é escolha, não imposição.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
