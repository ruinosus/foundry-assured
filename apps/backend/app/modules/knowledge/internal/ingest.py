"""Phase 1 ingestion: build the Foundry IQ knowledge base.

Run once (and again whenever the corpus changes), after `azd up`:

    cd backend
    uv run python -m app.modules.knowledge.internal.ingest

Steps:
  1. Upload every markdown in corpus/ to the blob container.
  2. Create a blob *knowledge source* (Azure AI Search auto-chunks + embeds it
     using the Foundry embedding deployment, via the search managed identity).
  3. Create the *knowledge base* that orchestrates agentic retrieval over that
     source, using gpt-5-mini for query planning + answer synthesis.

Auth is DefaultAzureCredential throughout (no keys). The deploying user needs
Search Service Contributor + Storage Blob Data Contributor (granted by the
Bicep); the search managed identity reaches the model + blobs via its own roles.

SDK surface verified against azure-search-documents 11.7.0b2.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import sys
import time
from pathlib import Path

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureBlobKnowledgeSource,
    AzureBlobKnowledgeSourceParameters,
    AzureOpenAIVectorizerParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeSourceAzureOpenAIVectorizer,
    KnowledgeSourceIngestionParameters,
    KnowledgeSourceReference,
)
from azure.storage.blob import BlobServiceClient

import app as _app
from app.modules.knowledge.internal import frontmatter
from app.modules.knowledge.internal.acl_setup import _component
from app.modules.tenancy.public import tenant_config

# Anchored on the `app` package, NOT on this file (RULE #9). `Path(__file__).parent / "corpus"`
# was correct while this module sat at `app/knowledge/ingest.py`; ADR-017 moved it one level
# down into `internal/` and the path silently began pointing at `internal/corpus`, which does
# not exist — the corpus stayed where it was. Ingestion then exited with "No markdown found"
# instead of uploading the 13 runbooks. The fourth path to break this way in this repo.
#
# The corpus now lives at the repository root, in `knowledge/`, beside the wiki bundle. It is
# CONTENT, not code: it was inside the Python package only by accident of history, which is why
# nobody could find it. Nothing at runtime reads it — this module is a provisioning CLI.
CORPUS_DIR = Path(_app.__file__).resolve().parents[3] / "knowledge" / "corpus"


def _ks_name() -> str:
    """O nome do knowledge source do corpus — DA CONFIG, nunca de uma constante daqui.

    Era `KNOWLEDGE_SOURCE_NAME = "helpdesk-runbooks-ks"` neste módulo. Virou config porque o
    catálogo de domínios precisa do MESMO nome para rotear a recuperação, e `domains` não pode
    importar `knowledge.internal` (ADR-017). Duas constantes com o mesmo valor divergiriam no
    primeiro rename — e a divergência não daria erro: o ingest criaria um KS e o catálogo
    apontaria para outro, o que aparece como "o helpdesk não acha nada".

    Função e não constante de módulo porque no modo `shared` `tenant_config()` só existe DENTRO
    de uma requisição; lido no import, quebraria o boot."""
    return tenant_config().helpdesk_knowledge_source


# Per-call wall-clock budget. The create/update REST calls should return in
# seconds; if they hang, fail fast with the HTTP log instead of blocking forever.
CALL_TIMEOUT_S = int(os.environ.get("INGEST_CALL_TIMEOUT", "90"))


def _setup_logging() -> None:
    """Show the Azure SDK HTTP request/response lines so we can see where it hangs.

    Set INGEST_DEBUG=1 for full DEBUG (request/response bodies + headers).
    """
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    http_level = logging.DEBUG if os.environ.get("INGEST_DEBUG") else logging.INFO
    logging.getLogger(
        "azure.core.pipeline.policies.http_logging_policy"
    ).setLevel(http_level)


def _with_timeout(label: str, fn, timeout_s: int = CALL_TIMEOUT_S):
    """Run a blocking SDK call with a hard wall-clock timeout.

    On timeout we hard-exit (os._exit) so a stuck request thread can't keep the
    process alive; the HTTP log above points at the offending request.
    """
    print(f"  -> {label} (timeout {timeout_s}s)...", flush=True)
    started = time.monotonic()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        result = future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        print(
            f"  !! {label} TIMED OUT after {timeout_s}s — the call never returned.\n"
            f"     Look at the last 'Request URL' logged above: that request is hanging.\n"
            f"     Common causes: the search service can't reach the embedding endpoint\n"
            f"     (managed-identity role not yet effective, or wrong AZURE_AI_OPENAI_ENDPOINT),\n"
            f"     or a wrong api-version. Inspect the Search service in the Azure portal.",
            flush=True,
        )
        os._exit(1)
    executor.shutdown(wait=False)
    print(f"  <- {label} ok ({time.monotonic() - started:.1f}s)", flush=True)
    return result


def _require(name: str, value: str) -> str:
    if not value:
        sys.exit(
            f"Missing {name}. Populate backend/.env from `azd env get-values` "
            f"(see the README Phase 1 steps)."
        )
    return value


def preparar_corpus(files: list[Path]) -> tuple[list[tuple[str, bytes]], dict[str, list[str]]]:
    """(blobs a subir, acesso declarado por documento) — puro, sem rede. Testável.

    DUAS COISAS ACONTECEM AQUI, e elas são o par que faz a fonte carregar o próprio acesso
    (ADR-031):

    1. O frontmatter é TIRADO DO CORPO. Ele é metadado de transporte; indexado, viraria YAML no
       corpus de retrieval, e o modelo passaria a citar `groups:` como se fosse conteúdo. Mesmo
       motivo pelo qual `adapt_openwiki` já o tira do bundle.
    2. O `groups` que ele declara é RECOLHIDO. Tirar do corpo nunca foi motivo para jogar fora —
       é justamente o que fazia o acesso de uma fonte não-código não ter onde morar, sobrando só
       o mapa externo `ACL_CLASSIFICATION`, que vive fora do versionamento e casa por convenção
       de chave. Aqui o acesso viaja COM o documento, versionado junto, como o padrão de mercado
       faz (Graph connectors, Kendra: a ACL é propriedade do item).

    A chave é `acl_setup._component(nome)`, a MESMA que o `setup_acl` usará para procurar — se
    fossem duas normalizações, o carimbo cairia num documento e a busca perguntaria por outro.
    Colisão de chave é ERRO: `_canonical` corta versão no fim (`github-2fa-recovery` → `github`),
    então dois arquivos podem colidir, e aí um acesso declarado sobrescreveria o outro em
    silêncio — que é a falha mais cara possível neste caminho.
    """
    blobs: list[tuple[str, bytes]] = []
    acesso: dict[str, list[str]] = {}
    origem: dict[str, str] = {}  # chave → arquivo que a produziu, só para a mensagem de colisão
    for path in files:
        texto = path.read_text(encoding="utf-8")
        try:
            meta, corpo = frontmatter.parse(texto)
        except frontmatter.FrontmatterInvalido as exc:
            sys.exit(f"{path.name}: {exc}")  # alto, nunca silencioso — pode ser acesso torto
        blobs.append((path.name, corpo.lstrip("\n").encode("utf-8")))

        grupos = frontmatter.declared_groups(meta)
        if grupos is None:
            continue  # não declara acesso — decide quem consome (None ≠ [])
        chave = _component(path.name)
        if chave in acesso and acesso[chave] != grupos:
            sys.exit(
                f"colisão de chave de acesso: '{origem[chave]}' e '{path.name}' viram ambos "
                f"'{chave}' e declaram grupos diferentes ({acesso[chave]} vs {grupos}). "
                f"Renomeie um dos dois — um sobrescreveria o outro sem erro."
            )
        acesso[chave], origem[chave] = grupos, path.name
    return blobs, acesso


def upload_corpus(credential: TokenCredential) -> tuple[int, dict[str, list[str]]]:
    account = _require("AZURE_STORAGE_ACCOUNT", tenant_config().azure_storage_account)
    container = tenant_config().azure_storage_container
    blob_service = BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net",
        credential=credential,
    )
    container_client = blob_service.get_container_client(container)

    files = sorted(CORPUS_DIR.glob("*.md"))
    if not files:
        sys.exit(f"No markdown found in {CORPUS_DIR}")

    blobs, acesso = preparar_corpus(files)
    for nome, dados in blobs:
        container_client.upload_blob(name=nome, data=dados, overwrite=True)
        print(f"  uploaded {nome}")
    declarados = f", {len(acesso)} com acesso declarado" if acesso else ", nenhum declara acesso"
    print(f"Uploaded {len(blobs)} documents to {account}/{container}{declarados}.")
    return len(blobs), acesso


def _validate_storage_resource_id(rid: str) -> None:
    ok = (
        rid.startswith("/subscriptions/")
        and "/resourceGroups/" in rid
        and "/providers/Microsoft.Storage/storageAccounts/" in rid
        and "..." not in rid
    )
    if not ok:
        sys.exit(
            "AZURE_STORAGE_RESOURCE_ID is not a full ARM resource id:\n"
            f"  {rid}\n"
            "It must look like /subscriptions/<sub>/resourceGroups/<rg>/providers/"
            "Microsoft.Storage/storageAccounts/<name> (no '...').\n"
            "Get the real value with:  azd env get-values | grep AZURE_STORAGE_RESOURCE_ID"
        )


def create_knowledge_source(index_client: SearchIndexClient) -> None:
    openai_endpoint = _require("AZURE_AI_OPENAI_ENDPOINT", tenant_config().azure_ai_openai_endpoint)
    storage_id = _require("AZURE_STORAGE_RESOURCE_ID", tenant_config().azure_storage_resource_id)
    _validate_storage_resource_id(storage_id)

    # ResourceId=<...>; tells Search to read blobs via its managed identity (keyless).
    knowledge_source = AzureBlobKnowledgeSource(
        name=_ks_name(),
        description="Internal engineering runbooks and policies (helpdesk corpus).",
        azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
            connection_string=f"ResourceId={storage_id};",
            container_name=tenant_config().azure_storage_container,
            ingestion_parameters=KnowledgeSourceIngestionParameters(
                embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                    azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                        resource_url=openai_endpoint,
                        deployment_name=tenant_config().foundry_embedding_model,
                        model_name=tenant_config().foundry_embedding_model,
                        # auth_identity omitted -> search service managed identity
                    )
                ),
            ),
        ),
    )
    _with_timeout(
        f"create knowledge source '{_ks_name()}'",
        lambda: index_client.create_or_update_knowledge_source(knowledge_source),
    )
    print(f"Knowledge source '{_ks_name()}' created/updated.")


def create_knowledge_base(index_client: SearchIndexClient) -> None:
    openai_endpoint = tenant_config().azure_ai_openai_endpoint
    kb_name = tenant_config().azure_search_knowledge_base

    knowledge_base = KnowledgeBase(
        name=kb_name,
        description="Helpdesk runbooks and policies for internal engineering support.",
        knowledge_sources=[KnowledgeSourceReference(name=_ks_name())],
        models=[
            KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=openai_endpoint,
                    deployment_name=tenant_config().foundry_model,
                    model_name=tenant_config().foundry_model,
                )
            )
        ],
        output_mode="answerSynthesis",
        answer_instructions=(
            "Answer only from the retrieved runbooks. Cite the source document for "
            "every claim. If the answer is not in the knowledge base, say you don't know."
        ),
        retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
    )
    _with_timeout(
        f"create knowledge base '{kb_name}'",
        lambda: index_client.create_or_update_knowledge_base(knowledge_base),
    )
    print(f"Knowledge base '{kb_name}' created/updated.")


def wait_for_ingestion(
    index_client: SearchIndexClient,
    timeout_s: int = 600,
    ks_name: str | None = None,  # None → _ks_name(); default de função lê config no import
) -> None:
    """Poll the knowledge source status until indexing settles (best-effort)."""
    ks_name = ks_name or _ks_name()  # resolvido AQUI: default de função leria config no import
    print("Waiting for indexing to complete (this can take a few minutes)...")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            status = index_client.get_knowledge_source_status(ks_name)
        except Exception as exc:  # noqa: BLE001 - status API is preview; tolerate gaps
            print(f"  (status check unavailable: {exc}); skipping wait.")
            return
        text = str(getattr(status, "status", status)).lower()
        print(f"  status: {text}")
        if any(s in text for s in ("success", "ready", "completed", "idle")):
            print("Ingestion looks complete.")
            return
        if "error" in text or "failed" in text:
            print("Ingestion reported an error — check the Azure portal.")
            return
        time.sleep(15)
    print("Timed out waiting; check the knowledge source status in the portal.")


def aplicar_acesso_declarado(acesso: dict[str, list[str]]) -> bool:
    """Carimba no índice o acesso que as FONTES declararam — e só se alguma declarou.

    O `if not acesso: return False` é a parte importante, e é o que torna esta mudança segura de
    mergear. Ligar o `permissionFilterOption` num índice cujos documentos não têm grupo nenhum
    faz o trim esconder TUDO (fail-closed, que é o comportamento certo e seria o desastre errado
    aqui): hoje nenhum runbook declara acesso, e o helpdesk é audiência única por decisão
    (`catalog.py:154`, ADR-031). Sem declaração, este passo é um no-op e o corpus segue como
    está — byte a byte.

    Quando a PRIMEIRA fonte declarar, o caminho existe e ela é carimbada. As que continuarem sem
    declarar caem em `acl_default_groups`; se ele estiver vazio, ficam invisíveis — fail-closed,
    correto, e avisado em voz alta abaixo, porque "o corpus sumiu" sem explicação seria pior que
    o próprio erro.

    O nome do índice é DERIVADO do knowledge source (`<ks>-index`), a mesma convenção que
    `ingest_docbundles` usa nos dois sentidos (linha 643, `removesuffix("-index")`) — uma segunda
    variável de configuração aqui seria a lista paralela que diverge no primeiro rename."""
    if not acesso:
        print("  · nenhuma fonte declara acesso — índice não é carimbado (corpus inalterado)")
        return False

    cfg = tenant_config()
    padrao = [g for g in cfg.acl_default_groups.split(",") if g.strip()]
    sem_declaracao = len(sorted(CORPUS_DIR.glob("*.md"))) - len(acesso)
    if sem_declaracao and not padrao:
        print(
            f"  ⚠️  {len(acesso)} fonte(s) declaram acesso e {sem_declaracao} não declaram, e "
            f"ACL_DEFAULT_GROUPS está vazio: as que não declaram ficarão INVISÍVEIS (fail-closed). "
            f"Declare o acesso nelas, ou defina ACL_DEFAULT_GROUPS."
        )

    from app.modules.knowledge.internal.acl_setup import setup_acl

    setup_acl(acesso, index=cfg.helpdesk_search_index, default_groups=padrao)
    return True


def main() -> None:
    _setup_logging()
    _require("AZURE_SEARCH_ENDPOINT", tenant_config().azure_search_endpoint)
    # A blob knowledge source that uses an LLM (gpt-5-mini query planning) needs
    # the 2026-05-01-preview API; the SDK default (2025-11-01-preview) is older.
    api_version = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")
    print(f"Search endpoint: {tenant_config().azure_search_endpoint}")
    print(f"OpenAI endpoint: {tenant_config().azure_ai_openai_endpoint}")
    print(f"Embedding: {tenant_config().foundry_embedding_model} | Chat: {tenant_config().foundry_model}")
    print(f"api-version: {api_version}")

    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(
        endpoint=tenant_config().azure_search_endpoint,
        credential=credential,
        api_version=api_version,
        logging_enable=True,  # emit HTTP request/response lines
        connection_timeout=20,
        read_timeout=CALL_TIMEOUT_S,
    )

    # Preflight: a lightweight GET isolates connectivity/auth from the create payload.
    print("== Preflight: list knowledge sources (auth + connectivity check) ==")
    _with_timeout(
        "list knowledge sources",
        lambda: [ks.name for ks in index_client.list_knowledge_sources()],
        timeout_s=30,
    )

    print("== Step 1/4: upload corpus ==")
    _, acesso = upload_corpus(credential)
    print("== Step 2/4: create knowledge source ==")
    create_knowledge_source(index_client)
    print("== Step 3/4: create knowledge base ==")
    create_knowledge_base(index_client)

    wait_for_ingestion(index_client)
    print("== Step 4/4: carimbar acesso declarado pelas fontes ==")
    aplicar_acesso_declarado(acesso)
    print("\nDone. The knowledge base is ready for agentic retrieval.")


if __name__ == "__main__":
    main()
