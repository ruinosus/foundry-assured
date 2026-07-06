"""Boot factories for artifact stores — mirror app.core.auth._make_tenant_store."""
from __future__ import annotations

from app.core.settings import settings


def make_artifact_store():
    if settings.artifact_store_backend == "memory":
        from app.artifacts.store import InMemoryArtifactStore

        return InMemoryArtifactStore()
    from azure.identity import DefaultAzureCredential

    from app.artifacts.store import TableArtifactStore

    if not settings.artifact_store_account_url:
        raise RuntimeError(
            "artifact_store_backend=table requires ARTIFACT_STORE_ACCOUNT_URL"
        )
    return TableArtifactStore(
        settings.artifact_store_account_url,
        settings.artifact_table,
        DefaultAzureCredential(),
    )


def make_content_store():
    if settings.artifact_store_backend == "memory":
        from app.artifacts.store import InMemoryContentStore

        return InMemoryContentStore()
    from azure.identity import DefaultAzureCredential

    from app.artifacts.store import BlobContentStore

    if not settings.artifact_blob_account_url:
        raise RuntimeError(
            "artifact_store_backend=table requires ARTIFACT_BLOB_ACCOUNT_URL"
        )
    return BlobContentStore(
        settings.artifact_blob_account_url,
        settings.artifact_container,
        DefaultAzureCredential(),
    )
