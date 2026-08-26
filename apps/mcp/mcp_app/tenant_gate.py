"""O tenant do chamador e o entitlement do domínio — UMA regra, agora quatro consumidores.

ESTE MÓDULO NÃO DECIDE NADA POR CONTA PRÓPRIA. Ele chama `tenancy.public.resolve_tenant_record`
e `tenancy.public.domain_enabled`, que são exatamente o que a dependency `require_domain` do
FastAPI chama (ADR-010). Reimplementar a regra aqui faria as superfícies discordarem sobre quem
pode ler o quê — e a divergência não daria erro, só serviria domínio não licenciado em silêncio
numa delas.

EXISTE PORQUE A REGRA JÁ ESTAVA EM UM LUGAR SÓ E FALTAVA NOS OUTROS TRÊS. Até aqui só a tool
`search_docs` resolvia tenant e cobrava entitlement; o resource `document://` e a completion não
faziam nem uma coisa nem outra. Medido, os dois ramos eram ruins: com um tenant resolvido sem
licença para o domínio, o resource SERVIA o conteúdo; e no estado real do modo `shared` — em que
nenhum tenant é resolvido, porque só a tool resolvia — toda leitura virava `domínio desconhecido`
e a completion devolvia `[]`. O resource estava morto no `shared`, disfarçado de erro de domínio.

RESOLVER E COBRAR ANDAM JUNTOS, e é por isso que `recusa_de_tenant` faz os dois numa chamada só.
Resolver sem cobrar serve domínio não licenciado, que é pior do que falhar — é o conserto
"óbvio" que alguém faria olhando só o sintoma (a leitura falhando por falta de tenant).

DEVOLVE MENSAGEM, NÃO EXCEÇÃO. Quem decide é o tenancy; quem traduz para o protocolo é cada
superfície — a tool levanta `ToolError`, o resource levanta `ResourceError`, a completion
devolve vazio. Levantar uma exceção daqui obrigaria as três a saber traduzi-la, e o texto da
recusa (que os gates comparam por igualdade exata) passaria a existir em três lugares.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.modules.tenancy.public import domain_enabled, resolve_tenant_record
from app.shared.settings import settings

#: A loja de tenants, empurrada pela composition root. `None` fora do modo shared — e aí nada de
#: tenant é resolvido, que é o comportamento byte-idêntico de self_hosted/dedicated.
_tenant_store: Callable[[str], Any] | None = None


def set_tenant_store(fn: Callable[[str], Any] | None) -> None:
    """Recebe da composition root a função que resolve um tid para o `TenantRecord` — só no modo
    shared. O seam é uma FUNÇÃO, não a loja em si, no mesmo espírito de `set_domain_registry`:
    quem chama não precisa saber que a loja tem `.get`."""
    global _tenant_store
    _tenant_store = fn


class _StoreAdapter:
    """Embrulha o seam (uma função `tid -> TenantRecord | None`) no vocabulário `.get(tid)` que
    `tenancy.resolve_tenant_record` espera — ela é compartilhada com o caminho web, que resolve
    contra um objeto de loja de verdade. Sem isso, `resolve_tenant_record` teria que aprender
    dois formatos de loja."""

    def __init__(self, fn: Callable[[str], Any]) -> None:
        self._fn = fn

    def get(self, tid: str) -> Any:
        return self._fn(tid)


def recusa_de_tenant(chamador, domain: str | None) -> str | None:
    """`None` se o chamador pode seguir; senão a MENSAGEM da recusa.

    Fora do modo shared devolve `None` sem tocar em nada — self_hosted/dedicated continuam
    byte-idênticos ao que eram antes de qualquer multi-tenancy existir.

    `domain=None` significa "só resolva o tenant": é o que a completion do argumento `domain`
    precisa, porque ela ainda não tem domínio nenhum para cobrar — ela filtra a lista com
    `licenciado()` logo depois, que é a MESMA `domain_enabled`.
    """
    if settings.deployment_mode != "shared":
        return None
    if _tenant_store is None:
        return "tenant store não registrado"
    if resolve_tenant_record(chamador, _StoreAdapter(_tenant_store)) is None:
        return "tenant não habilitado"
    if domain is not None and not domain_enabled(domain):
        return f"domínio não habilitado para o tenant: {domain}"
    return None


def licenciado(domain_id: str) -> bool:
    """O domínio está licenciado para o tenant JÁ RESOLVIDO desta requisição?

    Fora do shared, todo domínio é licenciado (não há tenant). Dentro do shared é a regra da
    ADR-010, a mesma de `recusa_de_tenant` — só que como predicado, para filtrar uma lista em
    vez de recusar uma chamada. Exige que `recusa_de_tenant` já tenha rodado: `domain_enabled`
    lê o tenant da requisição, e sem tenant resolvido é fail-closed (devolve False).
    """
    return settings.deployment_mode != "shared" or domain_enabled(domain_id)
