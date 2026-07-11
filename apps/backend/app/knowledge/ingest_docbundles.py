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
      uv run python -m app.knowledge.ingest_docbundles

SDK surface mirrors app/knowledge/ingest.py (azure-search-documents 11.7.0b2).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
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
    SearchIndexFieldReference,
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
)
from azure.storage.blob import BlobServiceClient

from app.core.tenant import tenant_config
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


def trigger_indexer(
    indexer_client: SearchIndexerClient, *, indexer_name: str | None = None, wait_s: int = 0, poll_s: int = 8
) -> None:
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
    name = indexer_name or INDEXER_NAME
    try:
        indexer_client.run_indexer(name)
    except HttpResponseError as e:
        if "already" not in str(e).lower():  # already in progress → fine
            raise
    if wait_s <= 0:
        print("  indexer triggered (runs async; index fills incrementally)")
        return
    waited = 0
    while waited < wait_s:
        st = indexer_client.get_indexer_status(name)
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


def purge_orphans(credential, container: str, *, index_name: str | None = None) -> None:
    """Delete index chunks whose source blob no longer exists.

    The indexer adds/updates from existing blobs but NEVER removes docs for deleted
    ones (no deletion-detection policy). When a bundle is regenerated, its old pages'
    blobs are deleted but their chunks linger in the index and keep being retrieved.
    We reconcile the index against the container. (Requires Search Index Data
    Contributor on the search service — Reader cannot delete documents.)

    On an **ACL-enabled** index a plain `search=*` is permission-trimmed to ZERO (no header →
    no group), which would silently purge nothing. We list the docs with
    `x-ms-enable-elevated-read` (bypasses the permission filter) so every chunk's source blob is
    seen; deletion is by key (`uid`) and isn't permission-filtered.
    """
    import urllib.request

    from azure.storage.blob import BlobServiceClient

    idx = index_name or INDEX_NAME
    api = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")
    endpoint = tenant_config().azure_search_endpoint.rstrip("/")
    account = _require("AZURE_STORAGE_ACCOUNT", tenant_config().azure_storage_account)
    cc = BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net", credential=credential
    ).get_container_client(container)
    live = {b.name for b in cc.list_blobs()}

    token = DefaultAzureCredential().get_token("https://search.azure.com/.default").token
    orphans, seen, skip = [], set(), 0
    while True:
        req = urllib.request.Request(
            f"{endpoint}/indexes/{idx}/docs/search?api-version={api}", method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "x-ms-enable-elevated-read": "true"},
            data=json.dumps({"search": "*", "select": "uid,blob_url", "top": 1000, "skip": skip}).encode(),
        )
        rows = json.load(urllib.request.urlopen(req, timeout=90)).get("value", [])
        if not rows:
            break
        for d in rows:
            blob = str(d.get("blob_url", "")).rsplit("/", 1)[-1]
            if blob and blob not in live and d["uid"] not in seen:
                orphans.append({"uid": d["uid"]})
                seen.add(d["uid"])
        skip += len(rows)
        if len(rows) < 1000:
            break
    if orphans:
        SearchClient(
            endpoint=tenant_config().azure_search_endpoint, index_name=idx,
            credential=credential, api_version=api,
        ).delete_documents(documents=orphans)
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
    account = _require("AZURE_STORAGE_ACCOUNT", tenant_config().azure_storage_account)
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


def create_knowledge_source(
    index_client: SearchIndexClient, *, ks_name: str | None = None, container: str | None = None, label: str | None = None
) -> None:
    # Defaults keep the cockpit path byte-identical; overrides steer a second domain (selfwiki).
    ks = ks_name or KNOWLEDGE_SOURCE_NAME
    cont = container or tenant_config().cockpit_storage_container
    lbl = label or DOMAIN_LABEL
    # ACL-SAFE: if the KS already exists, DO NOT re-create it. create_or_update_knowledge_source
    # regenerates the index schema WITHOUT the out-of-band `groups` permissionFilter field (added by
    # setup_acl), and Azure refuses to drop it ("Existing field(s) 'groups' cannot be deleted"). The
    # KS/index/indexer are one-time provisioning; a content refresh reuses them (upload + indexer).
    try:
        index_client.get_knowledge_source(ks)
    except ResourceNotFoundError:
        pass  # not provisioned yet → create below
    else:
        print(f"Knowledge source '{ks}' already exists — skipping create (preserves the ACL index).")
        return
    openai_endpoint = _require("AZURE_AI_OPENAI_ENDPOINT", tenant_config().azure_ai_openai_endpoint)
    storage_id = _require("AZURE_STORAGE_RESOURCE_ID", tenant_config().azure_storage_resource_id)
    _validate_storage_resource_id(storage_id)
    knowledge_source = AzureBlobKnowledgeSource(
        name=ks,
        description=f"{lbl} documentation (components + release).",
        azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
            connection_string=f"ResourceId={storage_id};",
            container_name=cont,
            ingestion_parameters=KnowledgeSourceIngestionParameters(
                embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                    azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                        resource_url=openai_endpoint,
                        deployment_name=tenant_config().foundry_embedding_model,
                        model_name=tenant_config().foundry_embedding_model,
                    )
                ),
            ),
        ),
    )
    _with_timeout(
        f"create knowledge source '{ks}'",
        lambda: index_client.create_or_update_knowledge_source(knowledge_source),
    )
    print(f"Knowledge source '{ks}' created/updated.")


def create_knowledge_base(index_client: SearchIndexClient) -> None:
    kb_name = tenant_config().cockpit_search_knowledge_base
    knowledge_base = KnowledgeBase(
        name=kb_name,
        description=f"{DOMAIN_LABEL} knowledge base for its grounded expert agent.",
        knowledge_sources=[KnowledgeSourceReference(name=KNOWLEDGE_SOURCE_NAME)],
        models=[
            KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=tenant_config().azure_ai_openai_endpoint,
                    deployment_name=tenant_config().foundry_model,
                    model_name=tenant_config().foundry_model,
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


# ---------------------------------------------------------------------------
# Task 2b — searchIndex-backed cockpit KB (over the EXISTING ACL-stamped index).
#
# NON-DESTRUCTIVE, REVERSIBLE cutover: this creates a SEPARATE knowledge source
# (kind: searchIndex) + KB *alongside* the legacy azureBlob `cockpit-kb`, both over
# the SAME already-built + ACL-stamped `cockpit-docbundles-ks-index`. Nothing about
# the blob KB/source or the index is deleted or rebuilt.
#
# Why: STEP 0.5 proved (empirically) the native Foundry IQ retrieve honors the per-user
# ACL header `x-ms-query-source-authorization` ONLY when the KB's knowledge source is
# kind: searchIndex — NOT azureBlob (the #44454 gap). SDK model calls below mirror the
# proven ones in eval/step0_searchindex_filter_probe.py (RULE #1 — not invented).
#
# Cutover = point cfg.cockpit_search_knowledge_base (env COCKPIT_SEARCH_KNOWLEDGE_BASE)
# at cfg.cockpit_searchindex_knowledge_base. Rollback = point it back. The index the
# searchIndex KB reads is the SAME one the blob indexer keeps fresh, so ongoing ingest
# continues to feed both KBs with no extra pipeline.
# ---------------------------------------------------------------------------


def create_searchindex_knowledge_source(index_client: SearchIndexClient) -> None:
    """Create/update the searchIndex knowledge source over the EXISTING ACL index.

    Reads the SAME `cockpit-docbundles-ks-index` the blob indexer already builds +
    ACL-stamps — the index is neither rebuilt nor re-stamped here. Mirrors the probe's
    SearchIndexKnowledgeSource / SearchIndexKnowledgeSourceParameters calls.
    """
    cfg = tenant_config()
    ks_name = cfg.cockpit_searchindex_knowledge_source
    index_name = cfg.cockpit_search_index
    knowledge_source = SearchIndexKnowledgeSource(
        name=ks_name,
        description=(
            f"{DOMAIN_LABEL} — searchIndex source over the EXISTING ACL-stamped index "
            f"'{index_name}'. Unlocks native agentic retrieve honoring the per-user ACL "
            "header (x-ms-query-source-authorization). Reads the same index the blob "
            "indexer keeps fresh; nothing rebuilt."
        ),
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=index_name,
            # source_data_fields → references[].sourceData can carry the blob_url + snippet
            # (the docKey is opaque), so citations resolve to a real source.
            source_data_fields=[
                SearchIndexFieldReference(name="blob_url"),
                SearchIndexFieldReference(name="snippet"),
            ],
        ),
    )
    _with_timeout(
        f"create searchIndex knowledge source '{ks_name}'",
        lambda: index_client.create_or_update_knowledge_source(knowledge_source),
    )
    print(f"searchIndex knowledge source '{ks_name}' created/updated (→ {index_name}).")


def create_searchindex_knowledge_base(index_client: SearchIndexClient) -> None:
    """Create/update the searchIndex-backed cockpit KB alongside the legacy blob KB.

    Same models + answer instructions as the blob KB, differing only in its (searchIndex)
    knowledge source. Not the ACTIVE KB until cfg.cockpit_search_knowledge_base is flipped
    to point here — so provisioning it is safe and does not disturb the running domain.
    """
    cfg = tenant_config()
    kb_name = cfg.cockpit_searchindex_knowledge_base
    ks_name = cfg.cockpit_searchindex_knowledge_source
    knowledge_base = KnowledgeBase(
        name=kb_name,
        description=(
            f"{DOMAIN_LABEL} knowledge base (searchIndex source) — native agentic "
            "retrieve + per-user ACL header. Cutover twin of the legacy blob cockpit-kb."
        ),
        knowledge_sources=[KnowledgeSourceReference(name=ks_name)],
        models=[
            KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=cfg.azure_ai_openai_endpoint,
                    deployment_name=cfg.foundry_model,
                    model_name=cfg.foundry_model,
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
        f"create searchIndex knowledge base '{kb_name}'",
        lambda: index_client.create_or_update_knowledge_base(knowledge_base),
    )
    print(f"searchIndex knowledge base '{kb_name}' created/updated.")


def provision_searchindex_kb() -> None:
    """Provision ONLY the searchIndex KB/KS over the existing index (no upload/indexer).

    Standalone entry point for the Task 2b cutover — the index already exists and is
    ACL-stamped by a prior full ingest, so this just adds the searchIndex-backed twin:
        uv run python -m app.knowledge.ingest_docbundles --searchindex-kb-only
    """
    _setup_logging()
    _require("AZURE_SEARCH_ENDPOINT", tenant_config().azure_search_endpoint)
    api_version = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")
    index_client = SearchIndexClient(
        endpoint=tenant_config().azure_search_endpoint,
        credential=DefaultAzureCredential(),
        api_version=api_version,
        logging_enable=True,
        connection_timeout=20,
        read_timeout=CALL_TIMEOUT_S,
    )
    print("== searchIndex cockpit KB (over EXISTING ACL index — non-destructive) ==")
    create_searchindex_knowledge_source(index_client)
    create_searchindex_knowledge_base(index_client)
    print(
        "\nDone. The searchIndex KB is provisioned ALONGSIDE the legacy blob cockpit-kb.\n"
        "Cut over by pointing COCKPIT_SEARCH_KNOWLEDGE_BASE at "
        f"'{tenant_config().cockpit_searchindex_knowledge_base}' (reversible — flip back to roll back)."
    )


# ---------------------------------------------------------------------------
# selfwiki — searchIndex-backed KB over the EXISTING selfwiki index.
#
# selfwiki is the dogfood domain: its corpus (this repo's own deep-wiki) is ingested by
# REUSING this module's blob pipeline verbatim via env overrides (COCKPIT_STORAGE_CONTAINER=
# selfwiki-corpus, KB_KNOWLEDGE_SOURCE=selfwiki-docbundles-ks, COCKPIT_SEARCH_KNOWLEDGE_BASE=
# selfwiki-kb — see docs/CASE-STUDY-SELFWIKI-DOGFOOD.md). That left selfwiki-kb on an azureBlob
# source, which the native retrieve (hardcoded kind:searchIndex) can't serve.
#
# This mirrors the cockpit Task 2b twin (create_searchindex_knowledge_source/_base above) for
# selfwiki: a SEPARATE searchIndex KS + KB (selfwiki-si-kb over selfwiki-docbundles-si-ks) over
# the SAME already-built selfwiki-docbundles-ks-index. selfwiki has NO per-user ACL, so this is a
# functional/recall unification (get it onto the native path), not a security change. NON-
# DESTRUCTIVE + REVERSIBLE: nothing about the legacy blob selfwiki-kb/source or the index changes;
# cutover = the registry points at selfwiki_searchindex_knowledge_base (flip back to roll back).
# ---------------------------------------------------------------------------

_SELFWIKI_LABEL = "foundry-helpdesk selfwiki (this repo's own deep-wiki)"


def create_selfwiki_searchindex_knowledge_source(index_client: SearchIndexClient) -> None:
    """Create/update the selfwiki searchIndex knowledge source over the EXISTING selfwiki index.

    Same SDK model calls as create_searchindex_knowledge_source (RULE #1), pointed at the selfwiki
    names. Reads selfwiki-docbundles-ks-index (already built by the blob indexer); nothing rebuilt.
    """
    cfg = tenant_config()
    ks_name = cfg.selfwiki_searchindex_knowledge_source
    index_name = cfg.selfwiki_search_index
    knowledge_source = SearchIndexKnowledgeSource(
        name=ks_name,
        description=(
            f"{_SELFWIKI_LABEL} — searchIndex source over the EXISTING index "
            f"'{index_name}'. Unifies selfwiki on the native agentic retrieve path "
            "(kind:searchIndex). No per-user ACL (single-audience). Reads the same index the "
            "blob indexer keeps fresh; nothing rebuilt."
        ),
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=index_name,
            source_data_fields=[
                SearchIndexFieldReference(name="blob_url"),
                SearchIndexFieldReference(name="snippet"),
            ],
        ),
    )
    _with_timeout(
        f"create searchIndex knowledge source '{ks_name}'",
        lambda: index_client.create_or_update_knowledge_source(knowledge_source),
    )
    print(f"searchIndex knowledge source '{ks_name}' created/updated (→ {index_name}).")


def create_selfwiki_searchindex_knowledge_base(index_client: SearchIndexClient) -> None:
    """Create/update the searchIndex-backed selfwiki KB alongside the legacy blob selfwiki-kb.

    Mirrors create_searchindex_knowledge_base for the selfwiki names + label. Not the ACTIVE KB
    until the registry points at selfwiki_searchindex_knowledge_base, so provisioning is safe.
    """
    cfg = tenant_config()
    kb_name = cfg.selfwiki_searchindex_knowledge_base
    ks_name = cfg.selfwiki_searchindex_knowledge_source
    knowledge_base = KnowledgeBase(
        name=kb_name,
        description=(
            f"{_SELFWIKI_LABEL} knowledge base (searchIndex source) — native agentic retrieve. "
            "Cutover twin of the legacy blob selfwiki-kb (no ACL; single-audience)."
        ),
        knowledge_sources=[KnowledgeSourceReference(name=ks_name)],
        models=[
            KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=cfg.azure_ai_openai_endpoint,
                    deployment_name=cfg.foundry_model,
                    model_name=cfg.foundry_model,
                )
            )
        ],
        output_mode="answerSynthesis",
        answer_instructions=(
            f"Responda APENAS com base nos documentos de {_SELFWIKI_LABEL} recuperados. Cite o "
            "componente e o documento-fonte de cada afirmação. Se a resposta não estiver na base, "
            "diga que não sabe — nunca invente."
        ),
        retrieval_reasoning_effort=KnowledgeRetrievalMediumReasoningEffort(),
    )
    _with_timeout(
        f"create searchIndex knowledge base '{kb_name}'",
        lambda: index_client.create_or_update_knowledge_base(knowledge_base),
    )
    print(f"searchIndex knowledge base '{kb_name}' created/updated.")


def provision_selfwiki_searchindex_kb() -> None:
    """Provision ONLY the selfwiki searchIndex KB/KS over the existing selfwiki index.

    Standalone entry point for the selfwiki cutover — the index already exists + is populated by a
    prior full selfwiki ingest, so this just adds the searchIndex-backed twin:
        uv run python -m app.knowledge.ingest_docbundles --selfwiki-searchindex-kb-only
    """
    _setup_logging()
    _require("AZURE_SEARCH_ENDPOINT", tenant_config().azure_search_endpoint)
    api_version = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")
    index_client = SearchIndexClient(
        endpoint=tenant_config().azure_search_endpoint,
        credential=DefaultAzureCredential(),
        api_version=api_version,
        logging_enable=True,
        connection_timeout=20,
        read_timeout=CALL_TIMEOUT_S,
    )
    print("== searchIndex selfwiki KB (over EXISTING selfwiki index — non-destructive) ==")
    create_selfwiki_searchindex_knowledge_source(index_client)
    create_selfwiki_searchindex_knowledge_base(index_client)
    print(
        "\nDone. The searchIndex selfwiki KB is provisioned ALONGSIDE the legacy blob selfwiki-kb.\n"
        "The domain registry points selfwiki at "
        f"'{tenant_config().selfwiki_searchindex_knowledge_base}' (reversible — repoint to roll back)."
    )


def _prune_stale_blobs(credential, container: str, *, keep: set[str]) -> None:
    """Delete blobs not in the current upload set (e.g. a prior version's pages).

    A version bump (v0.2.0 → v0.3.0) writes NEW blob names (the key embeds the version), so the
    old-version blobs linger in the container; the indexer would keep re-crawling them and the KB
    would serve stale + current side by side. Pruning them lets purge_orphans then reconcile the
    index. Safe for a single-domain container (selfwiki-corpus holds only selfwiki bundles).
    """
    account = _require("AZURE_STORAGE_ACCOUNT", tenant_config().azure_storage_account)
    cc = BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net", credential=credential
    ).get_container_client(container)
    if not cc.exists():
        return
    stale = [b.name for b in cc.list_blobs() if b.name not in keep]
    for name in stale:
        cc.delete_blob(name)
    print(f"  pruned {len(stale)} stale blob(s) from '{container}'" if stale
          else f"  no stale blobs in '{container}'")


def ingest_selfwiki() -> None:
    """Full CONTENT ingest for the **selfwiki** domain (this repo's own deep-wiki), steered to the
    selfwiki names — no COCKPIT_* env overrides, no risk of touching the cockpit searchIndex twin.

        uv run python -m app.knowledge.ingest_docbundles --selfwiki

    selfwiki is a PRIVATE single-audience KB: readable by everyone with app access = the app-users
    group (APP_USERS_GROUP_ID). Bundles default to this repo's docs/wiki (override COCKPIT_DOCBUNDLES).
    Uploads to selfwiki-corpus, ensures the blob KS that drives selfwiki-docbundles-ks-index (created
    once; skipped if it exists — ACL-safe), (re)provisions the ACTIVE searchIndex KB (selfwiki-si-kb),
    prunes prior-version blobs + reconciles the index, runs the indexer, then STAMPS every doc with the
    app-users group (permissionFilter trim ON). No redeploy — the /selfwiki agent reads the KB live.
    """
    _setup_logging()
    cfg = tenant_config()
    _require("AZURE_SEARCH_ENDPOINT", cfg.azure_search_endpoint)
    default_bundles = Path(__file__).resolve().parents[4] / "docs" / "wiki"
    docbundles = Path(os.environ.get("COCKPIT_DOCBUNDLES", str(default_bundles))).expanduser()
    if not docbundles.is_dir():
        sys.exit(f"selfwiki docbundles dir not found: {docbundles}")
    # The blob KS name derives the index + indexer; keep it in lock-step with cfg.selfwiki_search_index
    # (…-index) so the searchIndex KB reads exactly what this indexer fills.
    ks_name = cfg.selfwiki_search_index.removesuffix("-index")
    indexer_name = f"{ks_name}-indexer"
    audience = cfg.app_users_group_id  # the single private audience = everyone with app access

    api_version = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")
    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(
        endpoint=cfg.azure_search_endpoint, credential=credential, api_version=api_version,
        logging_enable=True, connection_timeout=20, read_timeout=CALL_TIMEOUT_S,
    )

    print("== selfwiki 1/5: collect + upload deep-wiki bundles ==")
    items, _ = collect_pages(docbundles)  # single-audience → per-doc manifest groups not used
    if not items:
        sys.exit(f"No pages found under {docbundles}")
    print(f"Collected {len(items)} pages from {docbundles}")
    upload(credential, cfg.selfwiki_storage_container, items)
    _prune_stale_blobs(credential, cfg.selfwiki_storage_container, keep={n for n, _ in items})

    print("== selfwiki 2/5: blob knowledge source (created once; skipped if it exists) ==")
    create_knowledge_source(
        index_client, ks_name=ks_name, container=cfg.selfwiki_storage_container, label=_SELFWIKI_LABEL
    )

    print("== selfwiki 3/5: searchIndex KS + KB (the ACTIVE native-path KB) ==")
    create_selfwiki_searchindex_knowledge_source(index_client)
    create_selfwiki_searchindex_knowledge_base(index_client)

    print("== selfwiki 4/5: run indexer ==")
    indexer_client = SearchIndexerClient(
        endpoint=cfg.azure_search_endpoint, credential=credential, api_version=api_version,
        connection_timeout=20, read_timeout=CALL_TIMEOUT_S,
    )
    if not audience:
        trigger_indexer(indexer_client, indexer_name=indexer_name)  # non-blocking
        print(
            "\n⚠️  APP_USERS_GROUP_ID unset — indexed but docs NOT re-stamped; the index keeps its "
            "existing groups. Set APP_USERS_GROUP_ID to enforce the app-users audience."
        )
        return
    # selfwiki IS ACL'd to the app-users group. Block on the indexer so the index has the new docs,
    # THEN reconcile deletions (prior-version chunks) and stamp — both after the index is populated.
    trigger_indexer(indexer_client, indexer_name=indexer_name, wait_s=900)
    purge_orphans(credential, cfg.selfwiki_storage_container, index_name=cfg.selfwiki_search_index)
    print("== selfwiki 5/5: stamp the app-users audience (permissionFilter trim) ==")
    from app.knowledge.acl_setup import setup_acl

    # Access is DATA (RULE #6) — pass {} (no per-doc map) so EVERY doc gets the single audience.
    setup_acl({}, index=cfg.selfwiki_search_index, default_groups=[audience])
    print(
        f"\nDone — selfwiki indexed + stamped to the app-users group ({audience}); trimming ENABLED. "
        f"Live in '{cfg.selfwiki_searchindex_knowledge_base}'. No redeploy needed."
    )


def main() -> None:
    if "--searchindex-kb-only" in sys.argv:
        provision_searchindex_kb()
        return
    if "--selfwiki-searchindex-kb-only" in sys.argv:
        provision_selfwiki_searchindex_kb()
        return
    if "--selfwiki" in sys.argv:
        ingest_selfwiki()
        return
    _setup_logging()
    _require("AZURE_SEARCH_ENDPOINT", tenant_config().azure_search_endpoint)
    docbundles_path = os.environ.get("COCKPIT_DOCBUNDLES", tenant_config().cockpit_docbundles_path)
    if not docbundles_path:
        sys.exit("Set COCKPIT_DOCBUNDLES to the aap-kb docbundles/ directory.")
    docbundles = Path(docbundles_path).expanduser()
    if not docbundles.is_dir():
        sys.exit(f"COCKPIT_DOCBUNDLES is not a directory: {docbundles}")

    api_version = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")
    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(
        endpoint=tenant_config().azure_search_endpoint,
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
    upload(credential, tenant_config().cockpit_storage_container, items)
    print("== Step 2/3: create knowledge source ==")
    create_knowledge_source(index_client)
    print("== Step 3/3: create knowledge base ==")
    create_knowledge_base(index_client)

    # Task 2b: provision the searchIndex-backed twin KB over the SAME index alongside the
    # blob KB (non-destructive). It's not the active KB until COCKPIT_SEARCH_KNOWLEDGE_BASE
    # is flipped to it, so creating it here disturbs nothing.
    print("== Step 3b/3: create searchIndex knowledge source + KB (cutover twin) ==")
    create_searchindex_knowledge_source(index_client)
    create_searchindex_knowledge_base(index_client)

    print("== Step 4/4: trigger indexer (async) + reconcile deletions ==")
    indexer_client = SearchIndexerClient(
        endpoint=tenant_config().azure_search_endpoint, credential=credential,
        api_version=api_version, connection_timeout=20, read_timeout=CALL_TIMEOUT_S,
    )
    # Purge removed-blob chunks now (safe any time — it only deletes docs whose source
    # blob is gone), then kick the indexer and return. The index fills incrementally
    # and is queryable during the run; blocking on the full ~1s/chunk embedding pass
    # just stalls the caller.
    purge_orphans(credential, tenant_config().cockpit_storage_container)

    # Phase 4: when access groups are configured, the ingest owns document-level ACL too,
    # stamping each doc with the read groups its source declared (component_groups, from
    # the manifests) — access follows the source, no classification in code. Stamping
    # needs the index populated, so run the indexer to completion first; otherwise keep
    # the fast non-blocking path.
    if tenant_config().acl_group_map:
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
