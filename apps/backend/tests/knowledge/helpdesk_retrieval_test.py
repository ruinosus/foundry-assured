"""O helpdesk sabe PARA ONDE recuperar — e o KS que o ingest cria é o que o catálogo aponta.

O DEFEITO QUE ISTO FECHA. `helpdesk/internal/graph.py:74` monta a recuperação com o nosso
`GroundedRetrieval` sempre que há usuário, e ele chama `retrieve()` com o `DomainSpec` do
catálogo. `retrieval.py:87` ramifica por `kb_name`; o spec do helpdesk não tinha nenhum, nem
`search_index`, nem `search_endpoint`. O fallback montava:

    /indexes/None/docs/search

Sem host e sem índice. A chamada falhava, o `except Exception` de `before_run` engolia, e o
agente respondia SEM CONTEXTO — com a Regra #4, virava recusa. Só acontecia com auth ligada:
sem usuário, o `AzureAISearchContextProvider` de reserva assume e funciona. Nenhum gate via.

O QUE ESTE MÓDULO COBRA:

1. todo domínio que passa por `retrieve()` sabe rotear — `kb_name` (nativo) OU
   `search_index` + `search_endpoint` (fallback). Derivado do catálogo, não de uma lista;
2. a URL do fallback do helpdesk não contém mais `None` nem começa com `/`;
3. o nome do knowledge source e o do índice guardam a convenção `<ks>-index` — porque o ingest
   cria o KS por um lado e o catálogo aponta o índice pelo outro, e os dois leem a config;
4. o helpdesk segue `document_access="session"` — declarar o índice NÃO mudou quem pode ler.

    uv run python -m tests.knowledge.helpdesk_retrieval_test
"""

from __future__ import annotations

import sys

from app.modules.domains.public import domain_spec, domain_specs
from app.modules.tenancy.public import tenant_config

_falhas: list[str] = []


def checar(nome: str, ok: bool, detalhe: str = "") -> None:
    _falhas.append(f"{nome} — {detalhe}") if not ok else None
    print(f"   {'·' if ok else '❌'} {nome}{'' if ok else f'  ({detalhe})'}")


def main() -> int:
    cfg = tenant_config()
    specs = list(domain_specs())
    checar("catálogo não-vazio (senão nada abaixo prova nada)", len(specs) > 0, f"{len(specs)}")

    print("\n1. todo domínio com recuperação sabe para onde ir")
    # `workflow` e `grounded` recuperam; `tool` não (o platform age por MCP, não por corpus).
    for d in specs:
        if d.kind == "tool":
            print(f"   · {d.id}: kind=tool — não recupera, fora de escopo")
            continue
        nativo = bool(d.kb_name)
        fallback = bool(d.search_index and d.search_endpoint)
        checar(
            f"{d.id} roteia ({'nativo' if nativo else 'fallback' if fallback else 'NENHUM'})",
            nativo or fallback,
            "sem kb_name e sem search_index+search_endpoint → /indexes/None/docs/search",
        )

    print("\n2. a URL do fallback do helpdesk é montável")
    h = domain_spec("helpdesk")
    url = f"{h.search_endpoint.rstrip('/')}/indexes/{h.search_index}/docs/search"
    checar("não contém 'None'", "None" not in url, url)
    checar("tem host (não começa com '/')", not url.startswith("/"), url)

    print("\n3. a convenção `<ks>-index` amarra ingest e catálogo")
    checar(
        "helpdesk_search_index == f'{helpdesk_knowledge_source}-index'",
        cfg.helpdesk_search_index == f"{cfg.helpdesk_knowledge_source}-index",
        f"{cfg.helpdesk_search_index!r} vs {cfg.helpdesk_knowledge_source!r}",
    )
    checar("o catálogo usa o MESMO ks da config", h.ks_name == cfg.helpdesk_knowledge_source,
           f"{h.ks_name!r} vs {cfg.helpdesk_knowledge_source!r}")
    checar("o catálogo usa o MESMO índice da config", h.search_index == cfg.helpdesk_search_index,
           f"{h.search_index!r} vs {cfg.helpdesk_search_index!r}")

    print("\n4. declarar o índice NÃO mudou quem pode ler")
    checar("helpdesk segue document_access='session'", h.document_access == "session",
           f"virou {h.document_access!r} — ligar o trim sem grupo declarado esconde TUDO")

    if _falhas:
        print(f"\n❌ {len(_falhas)} falha(s):")
        for f in _falhas:
            print(f"   - {f}")
        return 1
    print("\n✅ todo domínio que recupera sabe para onde, e o helpdesk segue 'session'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
