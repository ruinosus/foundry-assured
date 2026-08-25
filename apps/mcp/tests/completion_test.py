"""A completion sugere só o que existe — e só o que o chamador poderia abrir.

Autocompletar é um CANAL DE DIVULGAÇÃO, e é fácil esquecer disso: ele responde antes de
qualquer autorização de leitura acontecer. Duas propriedades, portanto:

1. **Nada de lista escrita à mão.** Os domínios sugeridos vêm do catálogo
   (`app.modules.domains.public.domain_specs`, empurrado pela composition root), com a mesma
   exclusão que a rota `/source` faz — domínio `kind == "tool"` não tem documento. Sugerir um
   domínio que depois recusa é pior que não sugerir nada: a pessoa tenta, recebe erro e culpa a
   pergunta.
2. **Nome de documento passa pelo trim de ACL.** As sugestões saem do `retrieve`, que já filtra
   sob a identidade de quem perguntou. Uma listagem do container devolveria todos os blobs e
   reconstruiria exatamente o oráculo que `authorized_document` se recusa a dar ("não
   distinguimos 'não existe' de 'não pode ler' DE PROPÓSITO"). Sem identidade, zero sugestões —
   fail-closed silencioso, porque um autocompletar não deve explodir.

    uv run python -m tests.completion_test
"""

from __future__ import annotations

import asyncio
import sys

import mcp_types

from app.shared import auth as shared_auth
from app.shared.settings import settings
from mcp_app import resources_knowledge


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


class _Token:
    def __init__(self, raw: str) -> None:
        self.token = raw
        self.claims = {"roles": ["Reader"], "preferred_username": "quem@exemplo.invalid"}


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
        settings.entra_tenant_id,
        settings.entra_api_client_id,
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
        resources_knowledge.retrieve = falso_retrieve
        resources_knowledge._token_do_chamador = lambda: _Token("token-do-chamador")
        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""

        # ── domínio: derivado do catálogo, sem os `tool` ─────────────────────────────────
        todos = _completar("domain", "")
        check(f"sugere os domínios com documento ({todos})", todos == ["helpdesk", "techdocs", "selfwiki"])
        check("e NUNCA um domínio `tool` (não tem documento)", "platform" not in (todos or []))
        check("filtra pelo que já foi digitado", _completar("domain", "self") == ["selfwiki"])
        check("prefixo sem correspondência devolve vazio", _completar("domain", "zz") == [])

        # ── nome do documento: só via retrieve, e só com o domínio já escolhido ──────────
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

        # ── fail-closed: sem identidade, zero sugestões (e nenhuma busca) ────────────────
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
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

        # ── o que não é comigo devolve None, não erro ────────────────────────────────────
        check("argumento desconhecido → None (o protocolo trata como vazio)", _completar("outro", "x") is None)
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
            settings.entra_tenant_id,
            settings.entra_api_client_id,
        ) = original
        shared_auth._current_user.set(None)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ a completion sugere o que existe, e só o que o chamador poderia abrir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
