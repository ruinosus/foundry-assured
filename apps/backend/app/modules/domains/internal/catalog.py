"""O CATÁLOGO DE DOMÍNIOS: quais assistentes existem, de que tipo, e como cada um está
configurado para o tenant da requisição atual.

Isto morava em `app/registry.py` — a camada de composição — e saiu de lá na Fase 0c, quando
`apps/mcp` passou a ser a única superfície MCP. O motivo é a pergunta que organiza este
repositório (ADR-017): *de que negócio esse arquivo é?* A resposta não é "wiring de FastAPI".
`DomainSpec`, `DOMAIN_KINDS` e `domain_spec` são o dado que responde "quais assistentes este
produto oferece, e com que base de conhecimento" — o gêmeo exato de `apps/frontend/lib/domains.ts`.
Quem monta rota (`app/registry.py`) e quem serve MCP (`apps/mcp/mcp_app/main.py`) são DOIS
consumidores desse mesmo dado; enquanto ele morava na composição, o segundo precisava importar
da composição do primeiro.

O que ficou para trás em `app/registry.py`: o loop de montagem e o `include_routers`. Isso É
wiring, e wiring é da composição.

Notas que sobreviveram à mudança de casa:

- `domain_specs()` lê `tenant_config()` PREGUIÇOSAMENTE — nada acontece no import. Chamar no
  boot quebraria o modo `shared`, onde nenhum tenant está resolvido antes da primeira
  requisição. `DOMAIN_KINDS` é a topologia ESTÁTICA justamente para poder ser lida no boot.
- Acesso é DADO (regra 6): o catálogo carrega `acl_group_map` (nome→objectID) e
  `document_access`; classificação nenhuma mora aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.tenancy.public import tenant_config


@dataclass(frozen=True)
class DomainSpec:
    """One registry row — the backend twin of a frontend Domain (domains.ts).

    ACL is DATA (RULE #6): `acl_group_map` is a name→objectID dict carried as data; the
    registry never classifies. A grounded spec MUST resolve to a `kb_name` OR a `search_index`
    (else the retrieval fallback would hit `.../indexes/None/docs/search`) — enforced in
    __post_init__.

    `document_access` é DECLARADO, não derivado: é ele — e só ele — que decide, na rota
    `GET /source/{domain_id}/{name}` (knowledge/internal/document.py), se a leitura do
    documento integral reautoriza pelo trim de ACL do índice (`"acl"`) ou se a sessão válida já
    exigida pela rota é a regra inteira (`"session"`). Antes deste campo, a decisão vinha da
    truthiness de `acl_group_map` — um valor de CONFIGURAÇÃO que, no modo shared, vem do tenant
    store. Configuração ausente (grupos vazios em runtime) rebaixava em silêncio um domínio que
    deveria ter ACL: o índice continuava carimbado, mas a rota parava de consultá-lo. O default
    é o SEGURO (`"acl"`) de propósito — esquecer de declarar não pode rebaixar ninguém.
    """

    id: str
    kind: Literal["grounded", "workflow", "tool"]
    instructions: str = ""
    kb_name: str | None = None
    ks_name: str | None = None  # KB's knowledge-source name (native path); None → defaults to kb_name
    search_index: str | None = None
    search_endpoint: str = ""
    corpus_container: str = ""  # container do blob que guarda o documento integral (rota /source)
    acl_group_map: dict | None = None  # name→objectID; None/empty → no ACL trim (no-op)
    document_access: Literal["acl", "session"] = "acl"  # ver docstring da classe
    hosted_agent_name: str | None = None

    def __post_init__(self) -> None:
        # A grounded domain with neither a KB nor a search index would fall through to
        # `.../indexes/None/docs/search` in retrieval — fail fast at registry build instead.
        if self.kind == "grounded" and not (self.kb_name or self.search_index):
            raise ValueError(
                f"grounded domain '{self.id}' must set kb_name or search_index"
            )
        # Mesma lógica para a rota de documento: um domínio que declara `document_access="acl"`
        # sem `search_index` faria `document.authorized_document` montar
        # `.../indexes/None/docs/search` na primeira requisição — falhe aqui, na construção do
        # registry, não na requisição de alguém.
        if self.document_access == "acl" and not self.search_index:
            raise ValueError(
                f"domain '{self.id}' declares document_access='acl' but has no search_index"
            )


# The TOPOLOGY: which domains exist and what kind each is. Static on purpose — it is the same
# for every tenant, so it can be read at boot, where no tenant is resolved yet. The per-tenant
# CONFIG (kb, index, ACL map) lives in `domain_specs()` and is resolved per request.
#
# Splitting the two is what makes `shared` + auth boot. `mount_domains` used to walk
# `domain_specs()`, which reads `tenant_config()`; under MultiTenantConfigProvider that raises at
# boot ("no tenant resolved for this request") because there is no request yet. Note that
# `_knowledge_configured()` and `platform_configured()` already returned early in shared mode
# for exactly this reason — the registry was the one place that had not followed the rule.
DOMAIN_KINDS: dict[str, str] = {
    "helpdesk": "workflow",
    "techdocs": "grounded",
    "selfwiki": "grounded",
    "platform": "tool",
    # O assistente do WIZARD (não do chat de domínio): ajuda a preencher o formulário de criação
    # e propõe valores pela tool de frontend `propose_field`. `tool` e não `grounded` porque só o
    # caminho do adapter repassa as tools do cliente ao agente — medido, ver
    # `modules/builder/internal/builder.py`.
    "builder": "tool",
    # ADR-020: a domain on a DIFFERENT runtime, mounted by the same loop. The registry
    # dispatches by kind and each branch calls its framework's own idiom — there is no adapter
    # making them look alike, because the frameworks move faster than such an adapter could be
    # maintained. `oncall` is LangGraph; the four above are Agent Framework.
    "oncall": "graph",
    # Gêmeo em deepagents — mesmo problema, harness diferente. Ver modules/deepcall/public.py.
    "deepcall": "graph",
}


def domain_spec(domain_id: str) -> DomainSpec:
    """The fully-configured spec for ONE domain, resolved against the CURRENT request's tenant.

    Called from inside a request handler, where the auth dependency has already resolved the
    tenant. Never call it at boot.
    """
    for spec in domain_specs():
        if spec.id == domain_id:
            return spec
    raise KeyError(f"unknown domain: {domain_id}")


def domain_specs() -> list[DomainSpec]:
    """The four configured domain specs, built from the current request's tenant config (read
    LAZILY here — NOT at import). Mirrors domains.ts row-for-row.

    Chamada de fora do módulo (o harness de eval e o gate do registry leem a lista inteira), por
    isso é nome público: era `_domains`, e o underscore mentia sobre o alcance dela.
    """
    from app.modules.agentdefs.public import (
        SELFWIKI_INSTRUCTIONS,
        TECHDOCS_INSTRUCTIONS,
    )

    cfg = tenant_config()
    return [
        DomainSpec(
            id="helpdesk",
            kind="workflow",
            hosted_agent_name=cfg.hosted_agent_name,
            # ATENÇÃO antes de reusar este container para outra coisa: `document_access="session"`
            # (linha abaixo) significa que QUALQUER sessão autenticada pode ler QUALQUER blob da
            # raiz deste container pelo nome, via `GET /source/helpdesk/{name}` — não há trim de
            # ACL nem `search_index` aqui contra o qual reautorizar (é o motivo do `"session"`).
            # Hoje isso não vaza nada porque o container só recebe os runbooks da ingestão
            # (conteúdo já público a quem usa o helpdesk); conversas e trilha de auditoria vivem em
            # containers SEPARADOS de propósito. Mas o container deixou de ser só "insumo de
            # ingestão" — ele é também "superfície de leitura autenticada". Antes de gravar
            # qualquer coisa sensível aqui (ou de apontar outro domínio pra ele), pergunte: "uma
            # sessão qualquer pode ler isto pelo nome?" — se a resposta for não, este não é o
            # container certo.
            corpus_container=cfg.azure_storage_container,
            # Sem ACL de documento: helpdesk não declara grupo em documento nenhum (não é fonte
            # com controle por documento) e não seta `search_index` — sessão válida é a regra.
            document_access="session",
        ),
        DomainSpec(
            id="techdocs",
            kind="grounded",
            instructions=TECHDOCS_INSTRUCTIONS,
            kb_name=cfg.techdocs_searchindex_knowledge_base,  # techdocs-si-kb (native searchIndex retrieve)
            ks_name=cfg.techdocs_searchindex_knowledge_source,  # techdocs-docbundles-si-ks
            search_index=cfg.techdocs_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            corpus_container=cfg.techdocs_storage_container,
            acl_group_map=cfg.acl_group_map,  # PARSED property (name→objectID), not the raw string
            document_access="acl",
        ),
        DomainSpec(
            id="selfwiki",
            kind="grounded",
            instructions=SELFWIKI_INSTRUCTIONS,
            kb_name=cfg.selfwiki_searchindex_knowledge_base,  # selfwiki-si-kb (native searchIndex retrieve)
            ks_name=cfg.selfwiki_searchindex_knowledge_source,  # selfwiki-docbundles-si-ks
            search_index=cfg.selfwiki_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            corpus_container=cfg.selfwiki_storage_container,
            # Single private audience = the app-users group (everyone with app access). Intentional
            # ACL (ADR/spec 2026-07-02): the self-wiki is stamped with this group; retrieval sends the
            # OBO header because this map is truthy. Empty APP_USERS_GROUP_ID → no map (dev/single-user).
            acl_group_map=({"app-users": cfg.app_users_group_id} if cfg.app_users_group_id else None),
            document_access="acl",
        ),
        # `document_access="session"`: sem `search_index` (kind="tool"), e `GET /source` já
        # devolve 404 pra domínio `tool` antes de tocar `authorized_document` (knowledge/api.py)
        # — mas declarar aqui, em vez de herdar o default, deixa explícito que este domínio não
        # tem ACL de documento, em vez de "esqueceu de configurar".
        DomainSpec(id="platform", kind="tool", document_access="session"),
    ]
