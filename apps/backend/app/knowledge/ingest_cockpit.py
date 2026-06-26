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
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
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

KNOWLEDGE_SOURCE_NAME = "cockpit-docbundles-ks"


def collect_pages(docbundles: Path) -> list[tuple[str, bytes]]:
    """Walk every bundle (manifest.json + pages/*.md) and return (blob_name, content).

    Each page's generic H1 ("Visão Geral do Repositório") is replaced with a
    component+version-qualified one so the KB cites a meaningful source, e.g.
    "cockpit-portal-api v2.1.1 — Visão Geral do Repositório".
    """
    items: list[tuple[str, bytes]] = []
    for manifest_path in sorted(docbundles.rglob("manifest.json")):
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        component = meta.get("component")
        version = meta.get("componentVersion") or meta.get("releaseVersion")
        key = meta.get("key") or manifest_path.parent.name
        # Skip the legacy unversioned bundle (a duplicate of the versioned ones).
        if not component and not version:
            continue
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
    return items


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
        description="Avanade Cockpit platform documentation (components + release).",
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
        description="Avanade Cockpit platform knowledge base for the Cockpit expert agent.",
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
            "Responda APENAS com base nos documentos do Cockpit recuperados. Cite o "
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
    items = collect_pages(docbundles)
    if not items:
        sys.exit(f"No pages found under {docbundles}")
    print(f"Collected {len(items)} pages from {docbundles}")
    upload(credential, settings.cockpit_storage_container, items)
    print("== Step 2/3: create knowledge source ==")
    create_knowledge_source(index_client)
    print("== Step 3/3: create knowledge base ==")
    create_knowledge_base(index_client)

    from app.knowledge.ingest import wait_for_ingestion

    wait_for_ingestion(index_client, ks_name=KNOWLEDGE_SOURCE_NAME)
    print("\nDone. The Cockpit knowledge base is ready for agentic retrieval.")


if __name__ == "__main__":
    main()
