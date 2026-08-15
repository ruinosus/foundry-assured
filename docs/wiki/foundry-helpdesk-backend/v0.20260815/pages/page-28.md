# Hosted selfwiki and cockpit agents

The repository's grounded hosted-agent pair lives in:

- [`apps/hosted-selfwiki/main.py`](../../apps/hosted-selfwiki/main.py)
- [`apps/hosted-cockpit/main.py`](../../apps/hosted-cockpit/main.py)

They are best documented together because they use the same packaging model: a single-identity, Responses-based, KB-grounded expert agent.

## Shared runtime pattern

Both files:

- create `DefaultAzureCredential()`
- build a `FoundryChatClient`
- build an `AzureAISearchContextProvider`
- create one grounded agent with `context_providers=[search]`
- set `default_options={"store": False}`
- serve with `ResponsesHostServer`

This means they are the hosted equivalent of live grounded domains, but without the FastAPI retrieve-then-synthesize seam.

## Hosted cockpit

`apps/hosted-cockpit/main.py` defines `COCKPIT_INSTRUCTIONS` inline as a mirror of `app/agents/prompts.COCKPIT_INSTRUCTIONS`.

Important behavior encoded in the prompt and setup:

- respond in Portuguese,
- ground exclusively in retrieved cockpit knowledge-base documents,
- cite component and document sources,
- prefer authoritative architecture docs in case of conflict,
- be exhaustive when listing items,
- use structured formatting and Mermaid for architectural answers,
- `retrieval_reasoning_effort="medium"` for agentic retrieval completeness.

## Hosted selfwiki

`apps/hosted-selfwiki/main.py` defines `SELFWIKI_INSTRUCTIONS` inline as a mirror of `app/agents/prompts.SELFWIKI_INSTRUCTIONS`.

Important behavior encoded there:

- answer as a specialist on this repository,
- ground exclusively in deep-wiki documents about the repo,
- cite area and document names and point to concrete modules when useful,
- prefer authoritative overview and architecture documents,
- use concise "not found" behavior instead of speculative gaps lists,
- be exhaustive when enumerating modules or endpoints,
- use tables and Mermaid when structure helps.

## What these hosted agents preserve

Compared with live grounded domains, the hosted selfwiki and cockpit agents preserve:

- the KB-grounded Q&A model,
- domain-specific answer discipline,
- hosted managed execution,
- structured expert identity encoded in prompts.

## What they do not preserve

They do not share the live grounded-domain implementation details from `services/grounded.py` and `services/retrieval.py`, including:

- backend-managed retrieve-then-synthesize composition,
- live AG-UI custom `sources` emission contract,
- live OBO caller identity,
- live FastAPI endpoint dependency handling.

That means changes to live grounded retrieval code do not automatically change hosted grounded runtime behavior unless the hosted containers are updated too.

## Deployment identity

The source comment in `apps/hosted-selfwiki/main.py` notes an important operational fact: the container managed identity can invoke hosted agents but may 403 on raw model inference. That is part of why the hosted-agent path is useful.

## Related pages

- Hosted agents overview
- Grounded domains
- Retrieval and ACL
