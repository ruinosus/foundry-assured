"""Nenhum índice com trim de ACL tem indexer agendado — senão o carimbo evapora sozinho.

Este gate existe porque o verificador que já existia não conseguia ver o defeito, por
construção. Ele roda logo depois da ingestão, dentro da janela em que o carimbo ainda está
lá, e mede um ESTADO. O defeito era de DURABILIDADE — o estado estava certo às 18:41 e
errado às 19:58, sem que nada rodasse no meio a não ser um relógio.

O que aconteceu em 2026-08-20, medido:

    18:26  ingest do selfwiki: upload -> indexer -> setup_acl carimba `groups`
    18:41  verificação do CI: 93 chunks, trim ok           -> VERDE
    19:58  agenda AUTOMÁTICA do indexer dispara, 19 itens  -> `groups` zerado
    21:12  domínio inteiro invisível para todo mundo, inclusive para quem ESTÁ no grupo

O mecanismo: o campo `groups` não existe no blob. Quem o escreve é `setup_acl`, por PATCH
direto no índice. O indexer reescreve o documento inteiro a partir do blob, então cada
execução dele apaga o campo. Com `permissionFilterOption: enabled`, documento sem grupo é
invisível para TODOS (fail-closed). Dois escritores para o mesmo campo, e o que tem relógio
ganha sempre.

A agenda não é decisão deste repositório: o `AzureBlobKnowledgeSource` cria o indexer com
`schedule` de ~1 dia por padrão do Azure. `_drop_schedule` (ingest_docbundles.py) a remove a
cada ingestão; este gate prova que ela não voltou — um KS recriado a traz de volta calada.

NÃO verifica visibilidade de documento: isso é o que os gates de access-control já fazem, e
é justamente a medição que passa dentro da janela. Aqui a invariante é de CONFIGURAÇÃO, que
não tem janela.

    uv run python -m eval.acl_durability_test
"""

from __future__ import annotations

import sys

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient

from app.modules.tenancy.public import tenant_config

API_VERSION = "2026-05-01-preview"


def _trimmed_indexes(index_client: SearchIndexClient) -> list[str]:
    """Índices que dependem de carimbo out-of-band para não ficarem mudos."""
    trimmed = []
    for index in index_client.list_indexes():
        if getattr(index, "permission_filter_option", None) == "enabled":
            trimmed.append(index.name)
    return sorted(trimmed)


def problems() -> list[str]:
    cfg = tenant_config()
    if not cfg.azure_search_endpoint:
        print("AZURE_SEARCH_ENDPOINT ausente — SKIP (gate precisa do serviço de Search).")
        return []
    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(cfg.azure_search_endpoint, credential, api_version=API_VERSION)
    indexer_client = SearchIndexerClient(cfg.azure_search_endpoint, credential, api_version=API_VERSION)

    indexers = {name: indexer_client.get_indexer(name) for name in indexer_client.get_indexer_names()}
    found: list[str] = []

    for index_name in _trimmed_indexes(index_client):
        # O KS deriva os nomes: `<ks>-index` e `<ks>-indexer` são irmãos.
        expected = f"{index_name.removesuffix('-index')}-indexer"
        indexer = indexers.get(expected)
        if indexer is None:
            found.append(f"{index_name}: trim ligado mas não achei o indexer '{expected}'")
            continue
        if indexer.schedule is not None:
            found.append(
                f"{expected}: agenda ativa ({indexer.schedule.interval}) sobre o índice "
                f"'{index_name}', que tem trim de ACL — a próxima execução apaga o carimbo"
            )
    return found


def main() -> int:
    found = problems()
    if found:
        print("❌ carimbo de ACL com prazo de validade:\n")
        for problem in found:
            print(f"  ✗ {problem}")
        print(
            "\n   Um indexer agendado sobre índice com `permissionFilterOption: enabled` torna"
            "\n   o trim temporário: o carimbo dura até a próxima execução da agenda, e some"
            "\n   sem erro nenhum. Remova a agenda (ingest_docbundles._drop_schedule) ou faça"
            "\n   a permissão vir da FONTE (indexer_permission_options, exige ADLS Gen2)."
        )
        return 1

    print("✅ nenhum índice com trim de ACL depende de um indexer agendado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
