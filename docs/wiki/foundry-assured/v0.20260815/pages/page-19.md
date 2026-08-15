The hosted helpdesk app packages the repository’s core helpdesk concept as a Foundry hosted agent serving the Responses protocol on port 8088. It is not a copy of the live backend workflow; it is a deliberately self-contained hosted variant.[`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L1-L16)

## Entrypoint and workflow construction

`main.py` creates a `FoundryChatClient`, a Search context provider, three workflow steps, and then wraps the workflow as an agent before serving it with `ResponsesHostServer`.[`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L53-L68) [`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L70-L108)

The workflow ordering still mirrors live helpdesk conceptually:

- triage
- retrieve
- resolve

but there is no escalation executor and no HITL interruption model.[`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L30-L50) [`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L95-L105)

## Config surface

The hosted helpdesk app reads configuration from environment variables, especially:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KNOWLEDGE_BASE`

It authenticates with `DefaultAzureCredential`, which in hosted deployment means the platform-injected agent identity.[`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L53-L60) [`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L62-L68)

## Non-parity with live helpdesk

The file is explicit about the features it drops relative to the live app:

- OBO user identity
- per-user memory
- human-in-the-loop escalation

Those are omitted because they do not fit the single-identity, request-response hosted model used here.[`apps/hosted-agent/main.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/hosted-agent/main.py#L8-L16)

## Backend bridge consumer

The frontend never calls the hosted helpdesk agent directly. The backend’s `/helpdesk-hosted` route calls `stream_agui(body, hosted_agent_name)` and re-emits the Responses stream as AG-UI events for CopilotKit.[`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L12-L26) [`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/hosted.py#L72-L105)

## Minimal validation

- `cd apps/backend && uv run python -m eval.hosted_build_test`

That is the narrowest repository-native check that this hosted packaging path still conforms to expectations.