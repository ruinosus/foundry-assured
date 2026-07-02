"""Create the Foundry memory store (run once, after `azd up`).

    cd backend
    uv run python -m app.memory_provision

The memory store is a Foundry resource (not provisioned by the Bicep). It uses a
chat model deployment to extract/summarize memories. FoundryMemoryProvider then
reads/writes per-user memories scoped by the signed-in user's object id.

API verified against azure-ai-projects 2.2.0: the async AIProjectClient exposes
`.beta.memory_stores` (BetaMemoryStoresOperations) with create/get; the sync
client has no memory operations.
"""

import asyncio

from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import MemoryStoreDefaultDefinition
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential

from app.core.settings import settings
from app.core.tenant import tenant_config


async def main() -> None:
    if not tenant_config().foundry_project_endpoint:
        raise SystemExit("FOUNDRY_PROJECT_ENDPOINT is not set (see backend/.env).")

    name = tenant_config().foundry_memory_store
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=tenant_config().foundry_project_endpoint, credential=credential
        ) as client,
    ):
        try:
            existing = await client.beta.memory_stores.get(name)
            print(f"Memory store '{existing.name}' already exists — nothing to do.")
            return
        except ResourceNotFoundError:
            pass

        store = await client.beta.memory_stores.create(
            name=name,
            definition=MemoryStoreDefaultDefinition(
                chat_model=tenant_config().foundry_model,
                embedding_model=tenant_config().foundry_embedding_model,
            ),
            description="Helpdesk per-user memory (developer preferences + recurring resolutions).",
        )
        print(f"Created memory store '{store.name}'.")


if __name__ == "__main__":
    asyncio.run(main())
