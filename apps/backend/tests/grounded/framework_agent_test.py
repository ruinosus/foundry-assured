"""O caminho grounded-como-agente monta certo — e nasce DESLIGADO.

O QUE ESTE GATE PODE E NÃO PODE PROVAR, dito antes de tudo porque é a parte que importa. Ele prova
a MONTAGEM: que o agente é construído como o publicado, com os providers e o middleware certos, e
que o caminho novo está desligado por default. Ele NÃO prova a conversa — essa é a única troca
desta série que não dá para verificar offline, porque toca OBO e ACL contra o serviço real.

E o modo de falha dessa parte não verificável não é "quebra": é **servir documento que a pessoa não
deveria ver**, ou 403 em silêncio. Por isso o caminho novo nasce atrás de `GROUNDED_VIA_FRAMEWORK`
e o antigo continua sendo o default — trocar o único caminho verificado por um não verificado, e só
depois testar, inverteria o ônus da prova no lugar mais caro de errar.

O ACEITE que falta, e que nenhum gate substitui: uma conversa real no domínio, conferindo que a
resposta cita e que o painel de evidências enche; e o `eval/access_control_test`, que precisa das
identidades de teste e prova que a ACL trima de fato.

POR QUE `FoundryAgent` E NÃO `FoundryChatClient`: o segundo não aceita `agent_name`, então o agente
falaria com o DEPLOYMENT DO MODELO e não com o agente PUBLICADO — a versão que o portal mostra
deixaria de responder, que é o estado que a SEGUNDA MÁXIMA proíbe. Este teste fixa essa escolha,
porque ela é invisível: as duas construções funcionam, e só uma mantém o portal sendo a fonte.
"""

from __future__ import annotations

import os
import sys
from typing import Any


class _DomainFalso:
    id = "selfwiki"
    kb_name = "kb"
    search_index = ""
    search_endpoint = ""


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    from app.modules.grounded.internal import framework_agent as fa

    # --- nasce desligado --------------------------------------------------------------------
    anterior = os.environ.pop("GROUNDED_VIA_FRAMEWORK", None)
    try:
        check("o caminho novo está DESLIGADO por default", not fa.via_framework())
        os.environ["GROUNDED_VIA_FRAMEWORK"] = "true"
        check("…e liga por variável de ambiente", fa.via_framework())
        os.environ["GROUNDED_VIA_FRAMEWORK"] = ""
        check("…e vazio vale como desligado", not fa.via_framework())
    finally:
        os.environ.pop("GROUNDED_VIA_FRAMEWORK", None)
        if anterior is not None:
            os.environ["GROUNDED_VIA_FRAMEWORK"] = anterior

    # --- a classe escolhida é a que fala com o agente PUBLICADO -----------------------------
    import inspect

    from agent_framework_foundry import FoundryAgent, FoundryChatClient

    params_agente = set(inspect.signature(FoundryAgent.__init__).parameters)
    params_cliente = set(inspect.signature(FoundryChatClient.__init__).parameters)
    check(
        "`FoundryAgent` aceita `agent_name` (fala com o agente PUBLICADO)",
        "agent_name" in params_agente,
    )
    check(
        "…e `FoundryChatClient` NÃO — é por isso que a escolha existe",
        "agent_name" not in params_cliente,
    )
    check(
        "`FoundryAgent` aceita os seams (providers + middleware)",
        {"context_providers", "middleware"} <= params_agente,
    )

    # --- a montagem passa o que tem de passar ------------------------------------------------
    capturado: dict[str, Any] = {}

    class _AgenteFalso:
        def __init__(self, **kwargs: Any) -> None:
            capturado.update(kwargs)

    original = None
    try:
        import agent_framework_foundry as pacote

        original = pacote.FoundryAgent
        pacote.FoundryAgent = _AgenteFalso
        fa.build_grounded_agent(_DomainFalso(), None, "thread-1")
    except Exception as exc:  # noqa: BLE001 — a montagem não deve exigir rede
        falhas.append(f"  a montagem levantou sem rede: {type(exc).__name__}: {exc}")
    finally:
        if original is not None:
            pacote.FoundryAgent = original

    if capturado:
        check("o agente é construído pelo NOME do domínio", capturado.get("agent_name") == "selfwiki")
        check(
            "…com a recuperação com ACL entre os providers",
            any(type(p).__name__ == "GroundedRetrieval" for p in capturado.get("context_providers") or []),
        )
        # A CAMADA IMPORTA: `FoundryAgent.middleware` é AGENT-level (a docstring do pacote diz
        # isso). Um `ChatMiddleware` ali é silenciosamente ignorado — medido, e o efeito em
        # produção foi token ZERADO numa conversa que gravou todo o resto. Este check fixa a
        # camada, não só a presença, porque a presença é o que enganou.
        from agent_framework import AgentMiddleware, ChatMiddleware

        mws = list(capturado.get("middleware") or [])
        check("…e com middleware de uso", bool(mws))
        check(
            "…na camada de AGENTE (ChatMiddleware aqui é ignorado em silêncio)",
            all(isinstance(m, AgentMiddleware) for m in mws)
            and not any(isinstance(m, ChatMiddleware) for m in mws),
        )
        # `agent_version` ausente é DELIBERADO: fixar versão aqui faria o republish deixar de ter
        # efeito, que é o oposto do que a SEGUNDA MÁXIMA quer.
        check("…e SEM versão fixa (o republish tem de valer)", not capturado.get("agent_version"))

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print("\n".join(f for f in falhas if f.startswith("  ")))
        return 1
    print(
        "\n✅ a montagem está correta e o caminho novo está desligado."
        "\n   FALTA O ACEITE QUE NENHUM GATE DÁ: uma conversa real + `eval/access_control_test`."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
