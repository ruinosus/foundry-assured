# Knowledge pipeline

The knowledge pipeline is the backend subsystem that turns source or markdown corpora into retrievable knowledge bases with measurable fidelity. It spans generation, adaptation, ingest, ACL setup, retrieval, and now a full-document confirmation API used by the UI when a user opens a cited source. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/public.py#L1-L17) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/api.py#L1-L24)

This pipeline feeds Grounded Domains, and its source-confirmation endpoint is surfaced in the frontend through the Assurance Console and Frontend API and Proxy Layer.

## Generation paths

The README still documents two wiki-generation paths for selfwiki: a Foundry pipeline implemented by `wiki_builder.py`, and Microsoft Agent Skills / OpenWiki-driven generation. `wiki_builder.py` itself keeps the local contract explicit: generate a faithful LLM wiki from real source, pace and bound the work, and emit the ingest bundle format that downstream ingestion already understands. Source [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L29-L34)

A key invariant remains that the bundle format is a contract, not a private dialect: manifests are validated against the vendored schema before write. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L14-L27) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L63-L64)

## Fidelity gate

`wiki_builder.py` still owns the deterministic fidelity gate. `_fidelity_report` normalizes citations, strips GitHub blob URL prefixes to repo-relative paths, rejects worktree citations, and scores resolved versus total citations. `_fidelity_floor()` reads the single source of truth from `eval/assurance.yaml`, where `build.fidelity_min` is `0.80`. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L87-L118) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L124-L163) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/eval/assurance.yaml#L16-L25)

`eval/wiki_fidelity_test.py` applies that same logic to externally generated bundles so OpenWiki outputs still go through the repository assurance floor. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/eval/wiki_fidelity_test.py#L1-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/eval/wiki_fidelity_test.py#L61-L99)

## OpenWiki adaptation

`adapt_openwiki.py` remains the OpenWiki-specific adapter. It reads `openwiki/` output, skips navigation and scaffold files, strips OKF front matter, flattens internal wiki-to-wiki links so they do not inflate fidelity, reads `.last-update.json` for documented commit and model metadata, and writes the standard bundle layout. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L1-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L46-L56) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L93-L145) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L158-L212)

The important boundary is unchanged: OpenWiki is only a producer. Local ingest, ACL, and assurance rules stay enforced inside the knowledge module.

## Ingestion and ACL stamping

`ingest_docbundles.py` still turns docbundle trees into Azure Blob-backed Search knowledge sources and knowledge bases. `collect_pages()` walks bundle manifests, rewrites titles for meaningful citation labels, and returns both page blobs and component-to-group maps declared by manifests. That group map is then used for ACL stamping, which is how “access follows the source” is enforced. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L58-L66) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L168-L218)

A subtle but important rule remains in `collect_pages()`: absent or null `groups` is not the same as empty `[]`. Missing means “no declaration; let external or default policy decide”, while empty means “nobody reads this”, which must stay fail-closed. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L194-L201)

## Retrieval assurance

The pipeline does not end at ingest. Retrieval ACL parity tests still prove that production retrieval preserves user-specific document visibility all the way through native retrieval and projection logic. That means generation, ACL stamping, and retrieval are one assurance chain rather than separate features. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L133-L142)

## Full-document confirmation API

This range added a new public read path: `GET /source/{domain_id}/{name}`. The route lives in `app.modules.knowledge.api`, is authenticated through the shared auth dependencies, resolves the domain through a composition-root-injected lookup, rejects `tool` domains, and serves `{name, url, content, truncated}` for the requested source document. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/api.py#L24-L55) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/api.py#L52-L113)

That endpoint exists to confirm evidence, not to bypass retrieval. The comments and tests lock in three externally visible rules:

- the route rechecks authorization on every read instead of trusting a prior citation; [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/document.py#L1-L26) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/knowledge/document_access_test.py#L1-L21)
- in shared mode it also applies `require_domain(domain_id)` before touching the document, so tenant entitlement and per-document ACL both participate in the access decision; [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/api.py#L64-L83) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/knowledge/document_api_test.py#L183-L219)
- responses are `Cache-Control: no-store`, because the endpoint serves ACL-controlled content and a shared cache would become a data leak. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/api.py#L85-L112) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/knowledge/document_api_test.py#L160-L181)

### `authorized_document()` seam

The core access rule lives in `internal/document.py`. `authorized_document(domain, name, user)` validates the blob name, derives the blob URL from tenant storage config plus the domain corpus container, and only runs the search-based authorization probe when `domain.document_access == "acl"`. Session-only domains therefore avoid an invalid ACL search path, while ACL domains fail closed if a user token cannot be attached. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/document.py#L35-L49) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/document.py#L106-L167)

That is the central invariant for document confirmation: **a citation never grants durable read rights by itself**. The user must still pass the same underlying authorization trim at click time. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/internal/document.py#L7-L25)

## Runtime flow

This diagram covers the new confirmation branch alongside the established ingest-and-retrieve flow.

```mermaid
flowchart TD
  A[Wiki or markdown corpus] --> B[adapt_openwiki or wiki_builder]
  B --> C[ingest_docbundles ACL stamping]
  C --> D[Search or Knowledge Base]
  D --> E[retrieve for grounded answer]
  E --> F[emit citation title/url/snippet/index]
  F --> G[/source domain name]
  G --> H[authorized_document recheck]
  H --> I[return full markdown content no-store]
```

## When to edit this page

Consult this page when you are changing:

- docbundle generation or adaptation contracts,
- ACL stamping semantics in ingest,
- retrieval authorization or projection,
- the `/source/*` document-confirmation path,
- fidelity or shelf gates for externally generated wiki bundles.

For response rendering and click behavior after the API returns, continue in Assurance Console.

## Focused validation

Start with:

- `cd apps/backend && uv run pytest tests/knowledge/document_api_test.py tests/knowledge/document_access_test.py tests/knowledge/retrieval_acl_parity_test.py`
- `cd apps/backend && uv run pytest eval/wiki_fidelity_test.py`

Conditional follow-up checks:

- `cd apps/backend && uv run pytest tests/knowledge/corpus_container_parity_test.py` when moving corpus containers or blob naming,
- `cd apps/backend && uv run pytest tests/knowledge/document_contar_autorizado_test.py` when changing the low-level authorized-count probe,
- frontend smoke through the source viewer only when the change crosses the backend/frontend boundary described in Assurance Console.
