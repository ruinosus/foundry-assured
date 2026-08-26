"""Item 2 da faxina: o `corpus_container` declarado no registry bate com o container que a
ingestão realmente usa — e o formato de URL que `document._blob_url` monta bate com o que o
SDK do Azure Blob Storage produz de verdade.

POR QUE ISTO IMPORTA. `document._blob_url(domain, name)` monta a URL do blob à MÃO
(`https://{conta}.blob.core.windows.net/{container}/{nome}`) a partir de `domain.corpus_container`
— nunca aceita a URL do chamador (SSRF). Nada garante estruturalmente que esse `container` é o
MESMO em que a ingestão (`ingest.py`/`ingest_docbundles.py`) realmente publicou os blobs: os dois
lados leem `tenant_config()` de forma independente. Se um dos dois apontar para o campo errado, a
consequência é **fail-closed silencioso**: todo `GET /source/{domínio}/*` vira 403/404 para
documentos que existem, e nada no caminho grita — é seguro, mas indiagnosticável sem abrir os dois
arquivos lado a lado.

O QUE ESTE TESTE PROVA, e como, sem tocar o Azure:

  1. FORMATO da URL: `document._blob_url` é comparado byte a byte com a URL que o SDK real
     (`azure.storage.blob.BlobServiceClient` → `ContainerClient.get_blob_client(name).url`)
     produziria para a MESMA conta/container/nome. `.url` é montagem de string local — não faz
     I/O — então isto roda sem credencial válida nem rede, e prova que o f-string manual não
     divergiu do que o SDK oficial (RULE #1: não inventar formato) realmente gera.

  2. WIRING do container: para os três domínios com blob real (helpdesk/techdocs/selfwiki), o
     campo `tenant_config().<attr>` que o catálogo de domínios atribui a `corpus_container=` é
     comparado, POR TEXTO-FONTE (o mesmo estilo de `tests/architecture/filesystem_anchors_test.py`
     — inspecionar a fonte real, não adivinhar comportamento), com o `tenant_config().<attr>` que
     `ingest.py`/`ingest_docbundles.py` usa para resolver o container em que o `upload`/
     `upload_corpus` realmente escreve. Os dois lados são só STRINGS DE ATRIBUTO — não dá pra
     rodar a ingestão de verdade sem Azure (ela cria índice, dispara indexador, stampa ACL), mas
     dá pra provar que as duas leituras independentes de config apontam para o MESMO campo, que é
     exatamente onde a divergência descrita no achado aconteceria (um dos dois apontando pro campo
     errado por typo/copy-paste).

O QUE ISTO NÃO PROVA (dito em vez de escondido): que o BLOB efetivamente existe naquele container
no Azure, ou que `AZURE_STORAGE_ACCOUNT` é o mesmo dos dois lados em produção (os dois leem
`tenant_config().azure_storage_account`, então não há segundo campo a divergir aí — só o
`container` varia por domínio). Ir além disso exigiria bater no Azure de verdade (fora do escopo
de um teste offline).

    uv run python -m tests.knowledge.corpus_container_parity_test
"""

from __future__ import annotations

import pathlib
import re
import sys

import app as _app
from app.modules.knowledge.internal import document
from app.modules.tenancy.public import TenantConfig

BACKEND = pathlib.Path(_app.__file__).resolve().parent.parent
_INGEST = BACKEND / "app" / "modules" / "knowledge" / "internal" / "ingest.py"
_INGEST_DOCBUNDLES = BACKEND / "app" / "modules" / "knowledge" / "internal" / "ingest_docbundles.py"
#: O CATÁLOGO, que saiu de `app/registry.py` na Fase 0c — é dele que sai `corpus_container=`.
_CATALOGO = BACKEND / "app" / "modules" / "domains" / "internal" / "catalog.py"


def main() -> int:
    print("corpus_container: formato de URL + wiring de container (item 2 da faxina)")
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'✓' if ok else '✗'} {nome}")
        if not ok:
            falhas.append(nome)

    # ── 1. FORMATO: _blob_url bate com o SDK real (sem rede, sem credencial válida) ──────────
    from azure.storage.blob import BlobServiceClient

    class _CredencialFalsa:
        def get_token(self, *a, **k):  # nunca chamado — .url não faz I/O
            raise NotImplementedError

    conta, container, nome = "acctxyz", "selfwiki-corpus", "page-11.md"
    domain = type("D", (), {"corpus_container": container})()

    # `tenant_config()` precisa devolver a conta usada acima — `_blob_url` lê
    # `tenant_config().azure_storage_account`. Patchamos o NOME IMPORTADO dentro de `document.py`
    # (mesmo padrão de `tests/knowledge/document_api_test.py`: trocar o atributo do MÓDULO que
    # consome, não a fonte) — mais cirúrgico que trocar o provider global de tenancy.
    original_tenant_config = document.tenant_config
    document.tenant_config = lambda: TenantConfig(azure_storage_account=conta)
    try:
        url_nossa = document._blob_url(domain, nome)
    finally:
        document.tenant_config = original_tenant_config

    svc = BlobServiceClient(
        account_url=f"https://{conta}.blob.core.windows.net", credential=_CredencialFalsa()
    )
    url_sdk = svc.get_container_client(container).get_blob_client(nome).url
    check("_blob_url bate byte a byte com a URL que o SDK real do Azure Blob produz", url_nossa == url_sdk)

    # ── 2. WIRING: o mesmo campo de config no catálogo e no lado da ingestão ────────────────
    catalogo_src = _CATALOGO.read_text()
    ingest_src = _INGEST.read_text()
    docbundles_src = _INGEST_DOCBUNDLES.read_text()

    def _campo_registry(domain_id_regex: str) -> str | None:
        """O atributo em `corpus_container=cfg.<attr>` da entrada de `domain_specs()` cujo bloco
        começa com `id="<domain_id_regex>"` — procurado dentro da fatia do source a partir da
        primeira ocorrência do id até a próxima `DomainSpec(` (ou fim do arquivo)."""
        m_id = re.search(rf'id="{domain_id_regex}"', catalogo_src)
        if not m_id:
            return None
        resto = catalogo_src[m_id.start():]
        prox = resto.find("DomainSpec(", 1)
        bloco = resto[:prox] if prox != -1 else resto
        m_campo = re.search(r"corpus_container=cfg\.(\w+)", bloco)
        return m_campo.group(1) if m_campo else None

    campo_helpdesk_registry = _campo_registry("helpdesk")
    campo_techdocs_registry = _campo_registry("techdocs")
    campo_selfwiki_registry = _campo_registry("selfwiki")

    m = re.search(r"container = tenant_config\(\)\.(\w+)", ingest_src)
    campo_helpdesk_ingest = m.group(1) if m else None

    m = re.search(r"upload\(credential, tenant_config\(\)\.(\w+), items\)", docbundles_src)
    campo_techdocs_ingest = m.group(1) if m else None

    m = re.search(r"upload\(credential, cfg\.(\w+), items\)", docbundles_src)
    campo_selfwiki_ingest = m.group(1) if m else None

    check(
        "encontrou os seis pontos de leitura (falha ALTO se algum sumiu/mudou de forma)",
        all([
            campo_helpdesk_registry, campo_techdocs_registry, campo_selfwiki_registry,
            campo_helpdesk_ingest, campo_techdocs_ingest, campo_selfwiki_ingest,
        ]),
    )
    check(
        f"helpdesk: registry.corpus_container ({campo_helpdesk_registry}) == "
        f"ingest.py container ({campo_helpdesk_ingest})",
        campo_helpdesk_registry == campo_helpdesk_ingest,
    )
    check(
        f"techdocs: registry.corpus_container ({campo_techdocs_registry}) == "
        f"ingest_docbundles.py upload() ({campo_techdocs_ingest})",
        campo_techdocs_registry == campo_techdocs_ingest,
    )
    check(
        f"selfwiki: registry.corpus_container ({campo_selfwiki_registry}) == "
        f"ingest_docbundles.py upload() ({campo_selfwiki_ingest})",
        campo_selfwiki_registry == campo_selfwiki_ingest,
    )

    print()
    if falhas:
        print(f"❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("✅ formato de URL confere com o SDK, e os três domínios apontam pro mesmo campo dos dois lados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
