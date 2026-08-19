"""`build_helpdesk_workflow` monta DE VERDADE — sem trocar a própria fábrica por um dublê.

POR QUE ISTO É GATE. Dois bugs derrubavam o domínio helpdesk, e nenhum gate existente pegaria
qualquer um dos dois:

BUG 1 — import quebrado. `graph.py` importava `domain_spec` de dentro do CORPO da função (import
adiado, não de topo de módulo), porque a chamada real só existe dentro da requisição. O nome do
símbolo estava errado (`app.modules.tenancy.public.domain_spec` não existe; o certo é
`app.registry.domain_spec`) e o módulo carregava normalmente — o `ImportError` só estourava
quando ALGUÉM USAVA o domínio, e derrubava o helpdesk inteiro em produção.

BUG 2 — incompatibilidade de tipo. `SourcesExecutor.on_retrieved` era tipado
`WorkflowContext[Any, Any]`. `Any` não é curinga para o VALIDADOR de grafo: `is_type_compatible`
rejeita a saída `Any` contra qualquer alvo concreto (mas aceita `Any` como ENTRADA — por isso a
aresta `retrieve -> sources` sempre passou e mascarou o problema do lado `sources -> resolve`).
`WorkflowBuilder.build()` só rejeitava essa aresta quando `SourcesExecutor` de fato entrava na
cadeia — o que só acontece com usuário autenticado E `domain_spec_provider` resolvendo, ou seja,
o BUG 1 quebrava ANTES de a cadeia chegar a expor o BUG 2. Consertar só um dos dois não bastava.

NENHUM gate existente pegaria qualquer um: `tests/smoke/routes_snapshot_test.py` e
`tests/registry/domain_registry_test.py` trocam `graph.build_helpdesk_workflow` por
`lambda *a, **k: object()` antes de montar, justamente para não precisar de Foundry — e um dublê
não executa o corpo que tinha o import quebrado, nem monta o grafo real que o validador rejeita.
Por desenho, os dois protegem outra coisa (o mapa de rotas e o despacho por `kind`), não a
fábrica em si.

Este teste chama a fábrica de verdade — com env sintético (sem rede: construir um
`FoundryChatClient`/`Agent` não chama a nuvem, só valida config) — em três formas: direto sem
provider, direto com provider + usuário resolvido (o ramo que expõe os dois bugs), e pela fiação
real de `app.registry._mount_helpdesk` (onde o fechamento que resolve o BUG 1 vive).

NO RAMO "com provider + usuário resolvido" A CHECAGEM É ESTRITA: `wf2` precisa ser um `Workflow`
de verdade, sem NENHUMA exceção — não só "não é ImportError/NameError". Uma versão anterior deste
teste aceitava qualquer erro que não fosse da classe do BUG 1, o que deixava o BUG 2
(TypeCompatibilityError) atravessar em silêncio. Além disso, o teste afirma que o executor
`sources` está DENTRO do grafo montado — sem essa asserção, um `Workflow` que monta mas sem
`SourcesExecutor` (por exemplo se `recuperacao` ficou `None` por engano) passaria pelo motivo
errado: o painel de evidências ficaria mudo, e o teste continuaria verde.
"""

from __future__ import annotations

import os
import sys

# Env sintético, não-secreto — só para os construtores locais (FoundryChatClient, AzureAISearch
# ContextProvider) aceitarem a config; nada disto alcança a rede. Blanking primeiro, mesmo padrão
# de tests/smoke/_capture_routes.py: hermético, não aditivo sobre o que já estiver no ambiente.
_ENV = {
    "DEPLOYMENT_MODE": "self_hosted",
    "FOUNDRY_PROJECT_ENDPOINT": "https://workflow-factory-test.invalid/api/projects/probe",
    "AZURE_SEARCH_ENDPOINT": "https://workflow-factory-test.invalid",
    "AZURE_SEARCH_KNOWLEDGE_BASE": "probe-kb",
    # Explicitamente vazio: `settings.auth_enabled` (app/shared/auth.py) é
    # `bool(entra_tenant_id and entra_api_client_id)`, e um `.env` de dev com Entra real (como
    # este repo tem) faria `credential_for_request()` tentar montar `OnBehalfOfCredential` com
    # `user_assertion=user.access_token` — exigindo um token de verdade no fake user. O que este
    # teste guarda (BUG 1 e BUG 2) não depende de qual credencial é construída, só de
    # `current_user() is not None`, que é setado direto no contextvar abaixo — então desligar
    # auth aqui mantém o teste hermético ao `.env` de quem roda, sem mudar o que ele prova.
    "ENTRA_TENANT_ID": "",
    "ENTRA_API_CLIENT_ID": "",
}


def _set_env() -> None:
    for key in _ENV:
        os.environ[key] = ""
    for key, value in _ENV.items():
        os.environ[key] = value


def main() -> int:
    _set_env()

    from agent_framework import Workflow

    from app import registry
    from app.modules.helpdesk.internal.graph import build_helpdesk_workflow
    from app.shared import auth

    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    # --- chamada direta, sem provider (o que a prova manual de teste/dev já faz) --------------
    try:
        wf = build_helpdesk_workflow("t1")
        erro = None
    except Exception as e:  # noqa: BLE001 — o ponto do check é justamente não levantar
        wf, erro = None, e
    check(
        "build_helpdesk_workflow('t1') monta um Workflow de verdade, sem provider"
        + (f" — {erro!r}" if erro else ""),
        isinstance(wf, Workflow),
    )

    # --- com provider + usuário no contextvar: exercita o ramo que quebrou em produção --------
    chamadas: list[int] = []

    class _SpecFalso:
        id = "helpdesk"

    class _UsuarioFalso:
        oid = "u-workflow-factory-probe"

    def _provider():
        chamadas.append(1)
        return _SpecFalso()

    token = auth._current_user.set(_UsuarioFalso())
    try:
        wf2 = build_helpdesk_workflow("t2", domain_spec_provider=_provider)
        erro2 = None
    except Exception as e:  # noqa: BLE001
        wf2, erro2 = None, e
    finally:
        auth._current_user.reset(token)

    # A checagem é ESTRITA: monta sem NENHUM erro. Uma checagem fraca ("não é ImportError/
    # NameError") deixaria passar o BUG 2 (TypeCompatibilityError do WorkflowBuilder.build()) —
    # foi exatamente essa fraqueza que permitiu o domínio continuar fora do ar para qualquer
    # usuário autenticado depois do BUG 1 já corrigido.
    check(
        "…com domain_spec_provider e usuário resolvido, monta um Workflow de verdade, sem erro"
        + (f" — {erro2!r}" if erro2 else ""),
        isinstance(wf2, Workflow),
    )
    check("…e o provider foi CHAMADO (o ramo da recuperação rodou, não só existiu)", chamadas == [1])
    # A recuperação só entra na cadeia quando `recuperacao is not None` (graph.py). Sem esta
    # asserção, um `wf2` que monta mas SEM `SourcesExecutor` passaria pelo motivo errado: o
    # painel de evidências ficaria sem fonte nenhuma, em silêncio.
    check(
        "…e o executor 'sources' está DENTRO do grafo montado (a cadeia com recuperação rodou)",
        isinstance(wf2, Workflow) and "sources" in wf2.executors,
    )

    # --- a fiação real: app.registry._mount_helpdesk fecha sobre domain_spec("helpdesk") ------
    # É AQUI que o BUG 1 de produção morava: `_mount_helpdesk` (composition root) empresta
    # `domain_spec` para a fábrica por fechamento. Só chamando essa fiação de ponta a ponta — sem
    # trocar `build_helpdesk_workflow` por dublê — se prova que ela funciona.
    capturado: dict = {}
    real_adapter = registry.add_agent_framework_fastapi_endpoint

    def _adapter_fake(app, *, agent=None, path=None, dependencies=None, **kw):
        capturado["agent"] = agent

    registry.add_agent_framework_fastapi_endpoint = _adapter_fake
    try:
        registry._mount_helpdesk(object(), "helpdesk")
    finally:
        registry.add_agent_framework_fastapi_endpoint = real_adapter

    agente = capturado.get("agent")
    check("_mount_helpdesk registrou o agente AG-UI", agente is not None)
    if agente is not None:
        # Sem usuário no contextvar: exercita só o BUG 1 (import/fechamento). O ramo com
        # usuário já foi coberto acima, direto — repetir aqui pela fiação completa exigiria
        # simular a dependência de auth do FastAPI, fora do escopo deste teste (ele guarda a
        # FÁBRICA, não o middleware de auth).
        try:
            wf3 = agente._resolve_workflow("t3")
            erro3 = None
        except Exception as e:  # noqa: BLE001
            wf3, erro3 = None, e
        check(
            "…e resolver o workflow por essa fiação também monta, sem ImportError"
            + (f" — {erro3!r}" if erro3 else ""),
            isinstance(wf3, Workflow),
        )

    if falhas:
        print(
            f"\n❌ {len(falhas)} verificação(ões) falharam. Um import adiado dentro da fábrica só"
            "\n   estoura quando o domínio helpdesk é USADO, e um WorkflowContext[Any, Any] só"
            "\n   estoura quando a cadeia com recuperação de fato monta — nenhum outro gate chama"
            "\n   a fábrica de verdade. Este teste existe para isso: chamar direto, com usuário"
            "\n   resolvido, e pela fiação do registry."
        )
        return 1
    print("\n✅ build_helpdesk_workflow monta de verdade — direto, com recuperação ativa, e pela fiação do registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
