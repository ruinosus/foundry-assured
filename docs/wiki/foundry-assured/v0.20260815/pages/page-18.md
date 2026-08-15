The cockpit and selfwiki hosted apps are parallel grounded-agent packages. Both serve the Responses protocol, both use `DefaultAzureCredential`, and both build a single grounded agent over a Search context provider rather than a workflow graph.[`apps/hosted-cockpit/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-cockpit/main.py#L1-L12) [`apps/hosted-selfwiki/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-selfwiki/main.py#L1-L12)

## Shared packaging pattern

Both entrypoints do the same high-level work:

1. load env vars
2. create `FoundryChatClient`
3. create `AzureAISearchContextProvider`
4. create one agent with prompt instructions and `context_providers=[search]`
5. serve it through `ResponsesHostServer`

[`apps/hosted-cockpit/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-cockpit/main.py#L56-L87) [`apps/hosted-selfwiki/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-selfwiki/main.py#L59-L87)

## Prompt and domain intent

The apps inline copies of the cockpit and selfwiki instructions because the backend package is not on the container path. Each file explicitly says to keep the hosted prompt mirror in sync with the live prompt source.[`apps/hosted-cockpit/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-cockpit/main.py#L25-L53) [`apps/hosted-selfwiki/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-selfwiki/main.py#L25-L56)

That means prompt edits in the live backend are not automatically inherited by the hosted twins; prompt parity is a maintenance task.

## Config and identity

Both hosted agents are configured entirely by env and authenticate with the hosted agent identity via `DefaultAzureCredential`. They depend on:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KNOWLEDGE_BASE`

[`apps/hosted-cockpit/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-cockpit/main.py#L56-L74) [`apps/hosted-selfwiki/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-selfwiki/main.py#L59-L75)

## Non-parity with live grounded domains

The live grounded domains run synthesis and retrieval as the signed-in user when auth is enabled, and they emit an AG-UI `sources` custom event for frontend evidence rendering. The hosted twins instead return a hosted-agent Responses stream under hosted identity. The frontend sees them only through the backend hosted bridge.[`apps/backend/app/services/grounded.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/grounded.py#L76-L84) [`apps/backend/app/services/grounded.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/grounded.py#L123-L140) [`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L72-L105)

## Minimal validation

- `cd apps/backend && uv run python -m eval.hosted_build_test`

That check covers the shared hosted-grounded packaging assumptions.