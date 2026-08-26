"""A completion exige papel, cobra tenant, e só sugere o que o chamador poderia abrir.

Autocompletar é um CANAL DE DIVULGAÇÃO, e é fácil esquecer disso: ele responde antes de
qualquer autorização de leitura acontecer — e, no FastMCP 4, antes de qualquer autorização
QUALQUER. `_on_complete` (`fastmcp/server/mixins/mcp_operations.py`) não roda check nenhum e
não resolve o `auth=` do template referenciado. Medido antes do conserto: token válido com
`roles: []` recebia `['runbook-secreto.md']`. Quatro propriedades, portanto:

1. **Papel do Entra, rodado à mão.** O mesmo objeto de gate que vai no `auth=` do resource
   (`resources_knowledge.completar.auth`), aplicado dentro do handler. Sem papel, zero
   sugestões — e nem se chega ao `retrieve`.
2. **Tenant e entitlement (ADR-010).** No modo `shared` a completion resolve o tenant pelo
   MESMO `mcp_app.tenant_gate` da tool e do resource, e só oferece domínio licenciado. Antes
   ela não resolvia nada: sem tenant, o catálogo não resolvia e a resposta era `[]` para todo
   mundo — mudo por acidente, não por política.
3. **Nada de lista escrita à mão, e UMA lista só para os dois argumentos.** Os domínios saem do
   catálogo (`app.modules.domains.public.domain_specs`, empurrado pela composition root). Era
   uma leitura diferente por argumento: `domain` oferecia tudo que não fosse `kind == "tool"`
   (incluindo `helpdesk`, `workflow`) e `name` só respondia para `grounded` — medido,
   `['helpdesk','techdocs','selfwiki']` para domínio e `[]` para nome em helpdesk. Sugerir um
   domínio que nunca completa é pior que não sugerir nada: a pessoa tenta, não recebe nada e
   culpa a pergunta.
4. **Nome de documento passa pelo trim de ACL.** As sugestões saem do `retrieve`, que já filtra
   sob a identidade de quem perguntou. Uma listagem do container devolveria todos os blobs e
   reconstruiria exatamente o oráculo que `authorized_document` se recusa a dar ("não
   distinguimos 'não existe' de 'não pode ler' DE PROPÓSITO").

    uv run python -m tests.completion_test
"""

from __future__ import annotations

import asyncio
import sys

import mcp_types
from fastmcp import FastMCP

from app.modules.tenancy.public import set_current_tenant
from app.shared import auth as shared_auth
from app.shared.settings import settings
from mcp_app import resources_knowledge, tenant_gate


class _Spec:
    def __init__(self, domain_id: str, kind: str) -> None:
        self.id = domain_id
        self.kind = kind


_CATALOGO = [
    _Spec("helpdesk", "workflow"),
    _Spec("techdocs", "grounded"),
    _Spec("selfwiki", "grounded"),
    _Spec("platform", "tool"),
]

#: O perfil com auth LIGADA. Sem ele `require_any_role` degrada aberto (dev local) e o gate de
#: papel não significaria nada — que é exatamente o buraco que a propriedade 1 fecha.
TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"


class _Token:
    def __init__(self, raw: str, roles=("Reader",), tid: str = "") -> None:
        self.token = raw
        self.claims = {
            "roles": list(roles),
            "preferred_username": "quem@exemplo.invalid",
            "oid": "o-1",
            "tid": tid,
        }


class _Registro:
    def __init__(self, tid, enabled, status="active"):
        self.tid = tid
        self.enabled_domains = enabled
        self.status = status


def _completar(nome: str, valor: str, contexto: dict | None = None):
    """Uma chamada de `completion/complete` sobre o template do documento."""
    return asyncio.run(
        resources_knowledge.completar(
            mcp_types.ResourceTemplateReference(uri=resources_knowledge.URI_DOCUMENTO),
            mcp_types.CompletionArgument(name=nome, value=valor),
            mcp_types.CompletionContext(arguments=contexto) if contexto else None,
        )
    )


def main() -> int:
    falhas: list[str] = []
    buscas: list[tuple] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (
        resources_knowledge.retrieve,
        resources_knowledge._token_do_chamador,
        resources_knowledge._domain_lookup,
        resources_knowledge._catalogo,
        resources_knowledge._template,
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.deployment_mode,
    )

    async def falso_retrieve(query, user, domain, *, top=8):
        buscas.append((query, getattr(user, "access_token", None), getattr(domain, "id", None)))
        return [
            {"index": 1, "source": "runbook-deploy.md", "url": "https://x/1", "snippet": "a"},
            {"index": 2, "source": "runbook-rollback.md", "url": "https://x/2", "snippet": "b"},
            {"index": 3, "source": "guia-oncall.md", "url": "https://x/3", "snippet": "c"},
        ]

    try:
        resources_knowledge.set_domain_registry(lambda d: None, lambda: list(_CATALOGO))
        # `register` é obrigatório: o gate de papel da completion roda contra o COMPONENTE de
        # verdade (`_template`), o mesmo que o FastMCP passaria ao avaliar o `auth=` do
        # resource. Sem template registrado a completion é fail-closed — e `register_completion`
        # se recusa a subir, que é o que impede um servidor com autocompletar mudo em silêncio.
        resources_knowledge.register(FastMCP("completion-test", tools=[]))
        resources_knowledge.retrieve = falso_retrieve
        settings.entra_tenant_id = TENANT
        settings.entra_api_client_id = CLIENT
        settings.deployment_mode = "self_hosted"

        # ── 1 · papel do Entra: o gate que o FastMCP não roda ────────────────────────────
        resources_knowledge._token_do_chamador = lambda: _Token("tok", roles=[])
        buscas.clear()
        sem_papel_dominio = _completar("domain", "")
        sem_papel_nome = _completar("name", "runbook", {"domain": "techdocs"})
        check(
            f"token SEM papel não recebe domínio nenhum ({sem_papel_dominio})",
            sem_papel_dominio == [],
        )
        check(f"token SEM papel não recebe nome nenhum ({sem_papel_nome})", sem_papel_nome == [])
        check("e nem chegou ao retrieve (o gate responde antes)", buscas == [])
        resources_knowledge._token_do_chamador = lambda: _Token("tok", roles=["Auditor"])
        check("papel desconhecido também não abre", _completar("domain", "") == [])

        # ── 2 · com papel, volta a sugerir ───────────────────────────────────────────────
        resources_knowledge._token_do_chamador = lambda: _Token("token-do-chamador")
        todos = _completar("domain", "")
        check(
            f"com papel, sugere os domínios que a completion sabe completar ({todos})",
            todos == ["techdocs", "selfwiki"],
        )
        check(
            "e NUNCA um domínio `tool` (não tem documento)", "platform" not in (todos or [])
        )
        check(
            "nem `helpdesk`: sem índice, o nome nunca completaria — uma lista só para os dois "
            "argumentos",
            "helpdesk" not in (todos or []),
        )
        check("filtra pelo que já foi digitado", _completar("domain", "self") == ["selfwiki"])
        check("prefixo sem correspondência devolve vazio", _completar("domain", "zz") == [])

        # ── 3 · nome do documento: só via retrieve, e só com o domínio já escolhido ──────
        check(
            "sem o domínio no contexto não há o que sugerir",
            _completar("name", "run") == [],
        )
        sugestoes = _completar("name", "runbook", {"domain": "techdocs"})
        check(
            f"com o domínio, sugere os documentos que o trim de ACL deixou passar ({sugestoes})",
            sugestoes == ["runbook-deploy.md", "runbook-rollback.md"],
        )
        check(
            "e a busca correu sob a identidade do CHAMADOR (é o que faz o trim ser dele)",
            buscas and buscas[-1][1] == "token-do-chamador",
        )
        check(
            "domínio sem base de conhecimento não é buscado (nada de índice `None`)",
            _completar("name", "x", {"domain": "helpdesk"}) == [],
        )
        check(
            "domínio `tool` também não",
            _completar("name", "x", {"domain": "platform"}) == [],
        )

        # ── 4 · modo shared: tenant resolvido e entitlement cobrado (ADR-010) ────────────
        loja = {
            "t-ok": _Registro("t-ok", ("techdocs",)),
            "t-sem": _Registro("t-sem", ("oncall",)),
        }
        settings.deployment_mode = "shared"
        tenant_gate.set_tenant_store(lambda tid: loja.get(tid))

        resources_knowledge._token_do_chamador = lambda: _Token("tok", tid="t-ok")
        licenciados = _completar("domain", "")
        check(
            f"shared · sugere só o domínio LICENCIADO para o tenant ({licenciados})",
            licenciados == ["techdocs"],
        )
        check(
            "shared · e completa nomes nele",
            _completar("name", "runbook", {"domain": "techdocs"})
            == ["runbook-deploy.md", "runbook-rollback.md"],
        )
        buscas.clear()
        check(
            "shared · domínio NÃO licenciado não completa nome",
            _completar("name", "runbook", {"domain": "selfwiki"}) == [],
        )
        check("shared · e não chegou ao retrieve", buscas == [])

        resources_knowledge._token_do_chamador = lambda: _Token("tok", tid="t-sem")
        check(
            "shared · tenant sem nenhum domínio licenciado não recebe sugestão",
            _completar("domain", "") == [],
        )
        resources_knowledge._token_do_chamador = lambda: _Token("tok", tid="t-inexistente")
        check(
            "shared · tenant desconhecido não recebe sugestão",
            _completar("domain", "") == [],
        )
        settings.deployment_mode = "self_hosted"
        tenant_gate.set_tenant_store(None)
        set_current_tenant(None)

        # ── 5 · fail-closed: sem identidade, zero sugestões (e nenhuma busca) ────────────
        resources_knowledge._token_do_chamador = lambda: None
        buscas.clear()
        check(
            "auth ligada + sem token → nenhuma sugestão de documento",
            _completar("name", "run", {"domain": "techdocs"}) == [],
        )
        check(
            "e nem chegou ao retrieve (nada de sugerir como a aplicação)",
            buscas == [],
        )

        # ── 6 · o que não é comigo devolve None, não erro ────────────────────────────────
        resources_knowledge._token_do_chamador = lambda: _Token("token-do-chamador")
        check(
            "argumento desconhecido → None (o protocolo trata como vazio)",
            _completar("outro", "x") is None,
        )
        fora = asyncio.run(
            resources_knowledge.completar(
                mcp_types.PromptReference(name="triage"),
                mcp_types.CompletionArgument(name="domain", value=""),
                None,
            )
        )
        check("referência de prompt → None (os prompts não têm argumentos)", fora is None)
    finally:
        (
            resources_knowledge.retrieve,
            resources_knowledge._token_do_chamador,
            resources_knowledge._domain_lookup,
            resources_knowledge._catalogo,
            resources_knowledge._template,
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.deployment_mode,
        ) = original
        tenant_gate.set_tenant_store(None)
        set_current_tenant(None)
        shared_auth._current_user.set(None)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ a completion exige papel, cobra tenant, e só sugere o que o chamador pode abrir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
