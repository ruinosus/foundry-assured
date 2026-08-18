"""A ÚNICA fábrica de `FoundryChatClient` do backend.

POR QUE ELA EXISTE. Havia cinco construções idênticas espalhadas — `helpdesk/agents.py`,
`grounded/concierge.py`, `platform_ops/platform.py`, `builder/builder.py`,
`knowledge/wiki_builder.py` — todas com os mesmos três argumentos. Cinco construções não são só
repetição: são cinco lugares onde cada agente decide por conta o que instrumentar. O painel de ROI
mostrou o preço disso — `selfwiki` com 656 tokens gravados e todos os outros domínios com zero,
porque só um caminho se lembrava de gravar. Instrumentar os que faltavam um a um garantiria que o
PRÓXIMO agente nascesse fora da contabilidade, que é exatamente como o bug nasceu.

Com uma fábrica, medir passa a ser propriedade de FALAR COM O MODELO, não de cada agente lembrar.

O MIDDLEWARE VEM DE FORA, e não por gosto: `conversations` importa `foundry`
(`conversations/internal/listing.py`), então `foundry` importar `conversations` fecharia um ciclo, e
o `import-linter` recusa. A saída é a que este repositório já usa para o mesmo problema — o
composition root, que pode importar tudo, ENTREGA a peça: `main.py` faz
`foundry.set_chat_middleware(conversations.usage_recorder)`, exatamente como já faz
`tenancy.set_server_catalog(...)`. Sem registro, a fábrica funciona e não instrumenta nada, que é
o comportamento correto para um teste que não quer telemetria.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

#: Fábricas de middleware entregues pelo composition root. Lista, não uma só: aprovação, gravação
#: de uso e o que vier depois são independentes entre si.
_middleware_factories: list[Callable[[], Any]] = []


def set_chat_middleware(*factories: Callable[[], Any]) -> None:
    """Registra as fábricas de middleware que TODO cliente vai carregar.

    Idempotente por substituição, não por acumulação: chamar duas vezes não duplica o middleware
    (o que contaria cada token duas vezes — um erro que não daria erro).
    """
    _middleware_factories.clear()
    _middleware_factories.extend(factories)


def chat_client(credential: Any, *, middleware: Sequence[Any] | None = None, **kwargs: Any):
    """O cliente de chat do Foundry, com o middleware global desta instalação já anexado.

    `middleware` do chamador é SOMADO ao global, nunca o substitui — era o risco óbvio desta
    refatoração: `platform_ops` passa o middleware de aprovação, e trocá-lo pelo global
    desarmaria o HITL de escrita em silêncio.
    """
    from agent_framework.foundry import FoundryChatClient

    from app.modules.tenancy.public import tenant_config

    cfg = tenant_config()
    globais = [fabrica() for fabrica in _middleware_factories]
    todos = [*globais, *(middleware or [])]
    return FoundryChatClient(
        project_endpoint=cfg.foundry_project_endpoint or None,
        model=kwargs.pop("model", None) or cfg.foundry_model,
        credential=credential,
        middleware=todos or None,
        **kwargs,
    )
