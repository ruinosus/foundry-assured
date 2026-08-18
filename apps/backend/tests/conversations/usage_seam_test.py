"""Todo cliente de chat carrega o gravador de uso — por construção, não por lembrança.

POR QUE ISTO É GATE, e é o gate mais importante desta mudança. O bug que ela conserta não foi um
esquecimento pontual: `record_usage` era chamado de UM arquivo, e o painel de ROI mostrava um
domínio com 656 tokens e todos os outros com zero. A causa era estrutural — cinco construções de
`FoundryChatClient` espalhadas, cada agente decidindo por conta o que instrumentar. Consertar os
que faltavam, um a um, deixaria a estrutura intacta e garantiria que o próximo agente nascesse
fora da contabilidade.

Então o que precisa ser verificado não é "o helpdesk grava". É:

  1. a fábrica é a ÚNICA porta — nenhum módulo constrói `FoundryChatClient` direto;
  2. todo cliente que sai dela carrega o middleware registrado;
  3. o middleware do chamador é SOMADO, não substituído — `platform_ops` passa o middleware de
     aprovação, e trocá-lo desarmaria o HITL de escrita em silêncio, que é pior que não medir;
  4. registrar duas vezes não duplica o middleware, o que contaria cada token duas vezes;
  5. sem conversa amarrada o gravador é no-op — é o caso do `wiki_builder`, que roda por CLI.

O item 1 é o que faz os outros valerem: sem ele, alguém adiciona uma sexta construção e nada
falha.
"""

from __future__ import annotations

import pathlib
import re
import sys

import app as _app

BACKEND = pathlib.Path(_app.__file__).resolve().parent.parent

#: A fábrica, e só ela, pode nomear o cliente do framework.
_PORTA = "app/modules/foundry/internal/chat.py"


def _construcoes_diretas() -> list[str]:
    """Arquivos que constroem `FoundryChatClient(` fora da fábrica."""
    achados = []
    for caminho in sorted((BACKEND / "app").rglob("*.py")):
        rel = caminho.relative_to(BACKEND).as_posix()
        if rel == _PORTA:
            continue
        if re.search(r"\bFoundryChatClient\s*\(", caminho.read_text(encoding="utf-8")):
            achados.append(rel)
    return achados


def main() -> int:
    from app.modules.conversations.public import (
        bind_conversation,
        bind_dependency,
        current_conversation,
        usage_recorder,
    )
    from app.modules.foundry.internal import chat as fabrica

    falhas: list[str] = []

    # (1) a fábrica é a única porta
    diretas = _construcoes_diretas()
    if diretas:
        falhas.append(
            "  estes arquivos constroem FoundryChatClient direto, fora da fábrica — o uso deles\n"
            "  não é medido, e é assim que o painel de ROI voltou a mostrar zero:\n"
            + "".join(f"    {d}\n" for d in diretas)
        )

    # (2) e (4) o registro anexa, e registrar de novo não duplica
    fabrica.set_chat_middleware(usage_recorder)
    fabrica.set_chat_middleware(usage_recorder)
    registradas = fabrica._middleware_factories
    if len(registradas) != 1:
        falhas.append(
            f"  registrar duas vezes deixou {len(registradas)} fábricas de middleware — cada token"
            " seria contado uma vez por duplicata"
        )

    # (3) o middleware do chamador é somado, não substituído
    sentinela = object()
    globais = [f() for f in fabrica._middleware_factories]
    somados = [*globais, *[sentinela]]
    if sentinela not in somados or len(somados) != len(globais) + 1:
        falhas.append("  o middleware do chamador não sobreviveu à soma com o global")

    # (5) sem conversa amarrada, no-op — e amarrada, é a conversa certa
    gravador = usage_recorder()
    if current_conversation() is not None:
        falhas.append("  havia conversa amarrada antes de qualquer requisição")
    if gravador._registrar(object()) is None:
        falhas.append("  o hook não devolveu a resposta — em streaming isso a descartaria")
    bind_conversation("helpdesk", "thread-1")
    if current_conversation() != ("helpdesk", "thread-1"):
        falhas.append(f"  a amarração não pegou: {current_conversation()!r}")

    # A dependência que amarra tem de estar em `domain_deps` do registry — se ela sair de lá, os
    # domínios continuam servindo e param de ser medidos, sem nada falhar.
    from app import registry

    # Checa o FATO, não o nome: a dependência tem de vir do módulo de CONVERSAS. Procurar pelo
    # nome da função quebrou quando ela mudou de casa — e um teste que falha por renomeação, sem o
    # comportamento ter mudado, ensina a gente a ignorá-lo.
    from app.modules.tenancy.public import domain_deps as deps_de_tenancy

    def _modulos(deps) -> set[str]:
        return {
            getattr(getattr(d, "dependency", None), "__module__", "") or "" for d in deps
        }

    do_registry = registry.domain_deps("helpdesk")
    if len(do_registry) != len(deps_de_tenancy("helpdesk")) + 1:
        falhas.append("  domain_deps não carrega mais EXATAMENTE uma dependência a mais que tenancy")
    if not any("conversations" in m for m in _modulos(do_registry)):
        falhas.append(
            "  nenhuma dependência de `conversations` em domain_deps — sem a amarração, os "
            "domínios seguem servindo e param de ser medidos, em silêncio"
        )

    # ── a amarração RODA, e sobrevive ao StreamingResponse ────────────────────────────────
    #
    # Dois modos de falha silenciosa, os dois já observados:
    #
    #   · sem a anotação `request: Request`, o FastAPI trata o parâmetro como QUERY PARAM e
    #     devolve 422 antes de chamar a função. Nas rotas reais isso fica mascarado, porque a
    #     autenticação responde 401 primeiro — a amarração simplesmente nunca roda, e nada falha;
    #   · toda resposta de agente é um `StreamingResponse`, e o corpo é iterado DEPOIS do handler.
    #     Se o contextvar não atravessasse, o gravador leria `None` em cada chamada de modelo e
    #     gravaria zero para sempre.
    from fastapi import Depends, FastAPI
    from fastapi.responses import StreamingResponse
    from fastapi.testclient import TestClient

    sonda = FastAPI()

    @sonda.post("/sonda", dependencies=[Depends(bind_dependency("sonda"))])
    async def _sonda():
        async def gerar():
            yield str(current_conversation())

        return StreamingResponse(gerar(), media_type="text/plain")

    resposta = TestClient(sonda).post("/sonda", json={"threadId": "t-1"})
    if resposta.status_code != 200:
        falhas.append(
            f"  a dependência de amarração não roda (HTTP {resposta.status_code}) — provável falta"
            " da anotação `request: Request`, que o FastAPI lê como query param"
        )
    elif resposta.text != "('sonda', 't-1')":
        falhas.append(
            f"  a conversa não sobreviveu ao StreamingResponse: {resposta.text!r} — o gravador"
            " leria None em toda chamada de modelo e gravaria zero em silêncio"
        )

    if falhas:
        print("❌ a medição de uso deixou de ser uniforme:")
        print("\n".join(falhas))
        return 1

    print("✅ toda porta para o modelo passa pela fábrica, e toda fábrica mede")
    print(f"   nenhuma construção direta de FoundryChatClient fora de {_PORTA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
