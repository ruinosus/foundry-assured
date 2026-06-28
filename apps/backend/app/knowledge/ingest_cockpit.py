"""Ingest the Cockpit doc-bundle corpus into its own Foundry IQ knowledge base.

A second domain alongside the helpdesk: the same Foundry IQ pattern, pointed at the
**Cockpit** platform docs (the `docbundles/` from the aap-kb project — ~250 markdown
pages across 21 components + the platform release). Builds a separate blob container,
knowledge source and knowledge base (`cockpit-kb`) so the Cockpit expert agent
retrieves only Cockpit content.

The corpus is INTERNAL (Avanade Cockpit platform docs) — this reads it from an
external path (`COCKPIT_DOCBUNDLES`) and ships it only to the cloud KB; the content
is never copied into this (public) repo.

Run (after the helpdesk infra exists):
    cd apps/backend
    COCKPIT_DOCBUNDLES=/path/to/aap-kb/apps/agent/docbundles \
      uv run python -m app.knowledge.ingest_cockpit

SDK surface mirrors app/knowledge/ingest.py (azure-search-documents 11.7.0b2).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.indexes.models import (
    AzureBlobKnowledgeSource,
    AzureBlobKnowledgeSourceParameters,
    AzureOpenAIVectorizerParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeRetrievalMediumReasoningEffort,
    KnowledgeSourceAzureOpenAIVectorizer,
    KnowledgeSourceIngestionParameters,
    KnowledgeSourceReference,
)
from azure.storage.blob import BlobServiceClient

from app.core.settings import settings
from app.knowledge.ingest import (
    CALL_TIMEOUT_S,
    _require,
    _setup_logging,
    _validate_storage_resource_id,
    _with_timeout,
)

# The mechanism is domain-generic: the SAME pipeline serves any doc-bundle corpus by
# pointing it at a different knowledge source / container / KB. Defaults are the Cockpit
# domain; the selfwiki domain (this repo's own deep-wiki) reuses this module verbatim by
# overriding KB_KNOWLEDGE_SOURCE + COCKPIT_STORAGE_CONTAINER + COCKPIT_SEARCH_KNOWLEDGE_BASE.
KNOWLEDGE_SOURCE_NAME = os.environ.get("KB_KNOWLEDGE_SOURCE", "cockpit-docbundles-ks")
DOMAIN_LABEL = os.environ.get("KB_DOMAIN_LABEL", "Avanade Cockpit platform")
# Foundry IQ derives these from the knowledge source name.
INDEXER_NAME = f"{KNOWLEDGE_SOURCE_NAME}-indexer"
INDEX_NAME = f"{KNOWLEDGE_SOURCE_NAME}-index"


def trigger_indexer(indexer_client: SearchIndexerClient, *, wait_s: int = 0, poll_s: int = 8) -> None:
    """Kick a fresh indexer run. **Non-blocking by default** (`wait_s=0`).

    The blob data source has NO change/deletion detection, and create_or_update of
    the knowledge source does not run the indexer immediately (it runs on a ~1d
    schedule). Relying on the existing status returns the *previous* run's state, so
    freshly uploaded blobs look ingested when they aren't — we drive the crawl
    explicitly.

    But the run itself is embedding-bound (~1s/chunk) and the index is queryable
    *incrementally while it runs*, so we do NOT block on completion: a big batch can
    take 10-20 min server-side and waiting for it just stalls the caller. Pass
    `wait_s > 0` only when you must confirm completion synchronously.
    """
    try:
        indexer_client.run_indexer(INDEXER_NAME)
    except HttpResponseError as e:
        if "already" not in str(e).lower():  # already in progress → fine
            raise
    if wait_s <= 0:
        print("  indexer triggered (runs async; index fills incrementally)")
        return
    waited = 0
    while waited < wait_s:
        st = indexer_client.get_indexer_status(INDEXER_NAME)
        running = st.status == "running" or (st.last_result and st.last_result.status == "inProgress")
        if not running and st.last_result:
            r = st.last_result
            print(f"  indexer run: {r.status} ({r.item_count} items, {r.failed_item_count} failed)")
            return
        time.sleep(poll_s)
        waited += poll_s
    print("  indexer still running (continuing; it finishes server-side)")


# Backwards-compatible alias (older callers).
run_and_wait_indexer = trigger_indexer


def purge_orphans(credential, container: str) -> None:
    """Delete index chunks whose source blob no longer exists.

    The indexer adds/updates from existing blobs but NEVER removes docs for deleted
    ones (no deletion-detection policy). When a bundle is regenerated, its old pages'
    blobs are deleted but their chunks linger in the index and keep being retrieved.
    We reconcile the index against the container. (Requires Search Index Data
    Contributor on the search service — Reader cannot delete documents.)
    """
    from azure.storage.blob import BlobServiceClient

    account = _require("AZURE_STORAGE_ACCOUNT", settings.azure_storage_account)
    cc = BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net", credential=credential
    ).get_container_client(container)
    live = {b.name for b in cc.list_blobs()}

    search = SearchClient(
        endpoint=settings.azure_search_endpoint, index_name=INDEX_NAME,
        credential=credential, api_version=os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview"),
    )
    orphans, seen = [], set()
    for d in search.search(search_text="*", select=["uid", "blob_url"]):
        blob = str(d.get("blob_url", "")).rsplit("/", 1)[-1]
        if blob and blob not in live and d["uid"] not in seen:
            orphans.append({"uid": d["uid"]})
            seen.add(d["uid"])
    if orphans:
        search.delete_documents(documents=orphans)
        print(f"  purged {len(orphans)} orphan chunks (source blob no longer in '{container}')")
    else:
        print("  no orphan chunks to purge")


def collect_pages(docbundles: Path) -> tuple[list[tuple[str, bytes]], dict[str, list[str]]]:
    """Walk every bundle (manifest.json + pages/*.md).

    Returns (items, component_groups): the (blob_name, content) pages, and the
    {component-key: [groups]} map declared by each manifest (the read access inherited
    from the source repo by wiki_builder) — fed to the ACL stamping. Access follows the
    source; this code never classifies.

    Each page's generic H1 ("Visão Geral do Repositório") is replaced with a
    component+version-qualified one so the KB cites a meaningful source, e.g.
    "cockpit-portal-api v2.1.1 — Visão Geral do Repositório".
    """
    from app.knowledge.acl_setup import _component

    items: list[tuple[str, bytes]] = []
    component_groups: dict[str, list[str]] = {}
    for manifest_path in sorted(docbundles.rglob("manifest.json")):
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        component = meta.get("component")
        version = meta.get("componentVersion") or meta.get("releaseVersion")
        key = meta.get("key") or manifest_path.parent.name
        # Skip the legacy unversioned bundle (a duplicate of the versioned ones).
        if not component and not version:
            continue
        if meta.get("groups"):
            component_groups[_component(f"{key}__x.md")] = meta["groups"]
        # Citation label: "component version" for elements; the manifest title for
        # the platform bundle (e.g. "Plataforma Cockpit 2.1.0").
        label = f"{component} {version}" if component else (meta.get("title") or key)
        bundle_dir = manifest_path.parent
        for page in meta.get("pages", []):
            page_file = bundle_dir / page.get("file", f"pages/{page['id']}.md")
            if not page_file.exists():
                continue
            body = page_file.read_text(encoding="utf-8")
            lines = body.split("\n")
            if lines and lines[0].startswith("# "):  # drop the generic original H1
                body = "\n".join(lines[1:]).lstrip("\n")
            title = page.get("title") or page["id"]
            content = f"# {label} — {title}\n\n{body}"
            blob = f"{key}__{page['id']}.md".replace("/", "-")
            items.append((blob, content.encode("utf-8")))
    return items, component_groups


def upload(credential, container: str, items: list[tuple[str, bytes]]) -> int:
    account = _require("AZURE_STORAGE_ACCOUNT", settings.azure_storage_account)
    blob_service = BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net", credential=credential
    )
    client = blob_service.get_container_client(container)
    if not client.exists():
        client.create_container()
        print(f"  created container '{container}'")
    for name, data in items:
        client.upload_blob(name=name, data=data, overwrite=True)
    print(f"Uploaded {len(items)} Cockpit pages to {account}/{container}.")
    return len(items)


def create_knowledge_source(index_client: SearchIndexClient) -> None:
    openai_endpoint = _require("AZURE_AI_OPENAI_ENDPOINT", settings.azure_ai_openai_endpoint)
    storage_id = _require("AZURE_STORAGE_RESOURCE_ID", settings.azure_storage_resource_id)
    _validate_storage_resource_id(storage_id)
    knowledge_source = AzureBlobKnowledgeSource(
        name=KNOWLEDGE_SOURCE_NAME,
        description=f"{DOMAIN_LABEL} documentation (components + release).",
        azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
            connection_string=f"ResourceId={storage_id};",
            container_name=settings.cockpit_storage_container,
            ingestion_parameters=KnowledgeSourceIngestionParameters(
                embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                    azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                        resource_url=openai_endpoint,
                        deployment_name=settings.foundry_embedding_model,
                        model_name=settings.foundry_embedding_model,
                    )
                ),
            ),
        ),
    )
    _with_timeout(
        f"create knowledge source '{KNOWLEDGE_SOURCE_NAME}'",
        lambda: index_client.create_or_update_knowledge_source(knowledge_source),
    )
    print(f"Knowledge source '{KNOWLEDGE_SOURCE_NAME}' created/updated.")


def create_knowledge_base(index_client: SearchIndexClient) -> None:
    kb_name = settings.cockpit_search_knowledge_base
    knowledge_base = KnowledgeBase(
        name=kb_name,
        description=f"{DOMAIN_LABEL} knowledge base for its grounded expert agent.",
        knowledge_sources=[KnowledgeSourceReference(name=KNOWLEDGE_SOURCE_NAME)],
        models=[
            KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=settings.azure_ai_openai_endpoint,
                    deployment_name=settings.foundry_model,
                    model_name=settings.foundry_model,
                )
            )
        ],
        output_mode="answerSynthesis",
        answer_instructions=(
            f"Responda APENAS com base nos documentos de {DOMAIN_LABEL} recuperados. Cite o "
            "componente e o documento-fonte de cada afirmação. Para perguntas de "
            "arquitetura ou que envolvem múltiplos componentes, priorize os documentos "
            "de ARQUITETURA/visão geral da plataforma (autoritativos) sobre resumos de "
            "componentes individuais, que podem conter imprecisões. Se a resposta não "
            "estiver na base, diga que não sabe — nunca invente."
        ),
        retrieval_reasoning_effort=KnowledgeRetrievalMediumReasoningEffort(),
    )
    _with_timeout(
        f"create knowledge base '{kb_name}'",
        lambda: index_client.create_or_update_knowledge_base(knowledge_base),
    )
    print(f"Knowledge base '{kb_name}' created/updated.")


def main() -> None:
    _setup_logging()
    _require("AZURE_SEARCH_ENDPOINT", settings.azure_search_endpoint)
    docbundles_path = os.environ.get("COCKPIT_DOCBUNDLES", settings.cockpit_docbundles_path)
    if not docbundles_path:
        sys.exit("Set COCKPIT_DOCBUNDLES to the aap-kb docbundles/ directory.")
    docbundles = Path(docbundles_path).expanduser()
    if not docbundles.is_dir():
        sys.exit(f"COCKPIT_DOCBUNDLES is not a directory: {docbundles}")

    api_version = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")
    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=credential,
        api_version=api_version,
        logging_enable=True,
        connection_timeout=20,
        read_timeout=CALL_TIMEOUT_S,
    )

    print("== Step 1/3: collect + upload Cockpit corpus ==")
    items, component_groups = collect_pages(docbundles)
    if not items:
        sys.exit(f"No pages found under {docbundles}")
    print(f"Collected {len(items)} pages from {docbundles}")
    upload(credential, settings.cockpit_storage_container, items)
    print("== Step 2/3: create knowledge source ==")
    create_knowledge_source(index_client)
    print("== Step 3/3: create knowledge base ==")
    create_knowledge_base(index_client)

    print("== Step 4/4: trigger indexer (async) + reconcile deletions ==")
    indexer_client = SearchIndexerClient(
        endpoint=settings.azure_search_endpoint, credential=credential,
        api_version=api_version, connection_timeout=20, read_timeout=CALL_TIMEOUT_S,
    )
    # Purge removed-blob chunks now (safe any time — it only deletes docs whose source
    # blob is gone), then kick the indexer and return. The index fills incrementally
    # and is queryable during the run; blocking on the full ~1s/chunk embedding pass
    # just stalls the caller.
    purge_orphans(credential, settings.cockpit_storage_container)

    # Phase 4: when access groups are configured, the ingest owns document-level ACL too,
    # stamping each doc with the read groups its source declared (component_groups, from
    # the manifests) — access follows the source, no classification in code. Stamping
    # needs the index populated, so run the indexer to completion first; otherwise keep
    # the fast non-blocking path.
    if settings.acl_group_map:
        print("== Step 5/5: indexer (blocking) + document-level ACL (access from source) ==")
        trigger_indexer(indexer_client, wait_s=900)
        from app.knowledge.acl_setup import setup_acl

        setup_acl(component_groups or None)
        print("\nDone (corpus indexed + per-document access stamped + trimming enabled).")
    else:
        trigger_indexer(indexer_client)  # non-blocking
        print(
            "\nDone (uploads + deletions reconciled). The indexer is running async —\n"
            "new pages appear in the KB incrementally over the next few minutes.\n"
            "(Configure access groups to also stamp document-level access.)"
        )


if __name__ == "__main__":
    main()
