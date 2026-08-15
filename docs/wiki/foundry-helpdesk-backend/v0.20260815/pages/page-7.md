# Knowledge pipeline and docbundle contract

The backend owns the pipeline that turns source-grounded documentation into the corpora consumed by grounded domains. That includes ingesting docbundles into search-backed knowledge bases, adapting OpenWiki output into the shared bundle format, validating manifests against the vendored contract, and generating wiki bundles with the backend's own Foundry-driven builder. [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L1-L19) [adapt_openwiki.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/adapt_openwiki.py#L1-L34) [docbundle_schema.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/docbundle_schema.py#L1-L30)

## Shared contract: `manifest.json`

The docbundle format is treated as an external contract, not a local convention. `docbundle_schema.py` explains that the contract is vendored as `docbundle.schema.json`, validated with `jsonschema`, and shared across readers and writers in different repositories. This matters because the backend both consumes bundles (`ingest_docbundles`, freshness/fidelity gates) and produces them (`wiki_builder`, `adapt_openwiki`). [docbundle_schema.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/docbundle_schema.py#L1-L30) [docbundle_schema.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/docbundle_schema.py#L70-L85)

One contract detail is operationally important: `groups: null` or absent means the bundle declares no access information and the ingest may decide, while `groups: []` explicitly means no group may read it. The ingest treats those cases differently, so writers must not collapse them. [docbundle_schema.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/docbundle_schema.py#L17-L25)

## Bundle adaptation from OpenWiki

`adapt_openwiki.py` adapts `openwiki/` output into the bundle format that the ingest already understands. It:

- locates the wiki output, defaulting to `<repo>/openwiki` [adapt_openwiki.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/adapt_openwiki.py#L58-L71)
- walks pages in navigation order using directory `index.md` files, then appends any content pages the indexes missed so no page is silently dropped [adapt_openwiki.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/adapt_openwiki.py#L93-L123)
- strips front matter because OKF metadata is transport, not retrieval content [adapt_openwiki.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/adapt_openwiki.py#L74-L91)
- flattens internal wiki-to-wiki markdown links to plain text so the fidelity gate is not polluted by navigation links that look like source citations [adapt_openwiki.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/adapt_openwiki.py#L125-L145)
- reads `.last-update.json` to preserve the commit and model that produced the wiki [adapt_openwiki.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/adapt_openwiki.py#L147-L155)
- validates the produced manifest before writing it [adapt_openwiki.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/adapt_openwiki.py#L183-L210)

## Ingestion and knowledge-source provisioning

`ingest_docbundles.py` is the operational ingest path for docbundle corpora. It is written so the same mechanism can serve multiple domains by overriding environment defaults such as `KB_KNOWLEDGE_SOURCE`, container name, or KB name. [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L58-L67)

The main duties are:

- collect pages from bundles and derive component-group metadata from manifests [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L168-L218)
- upload rendered pages to blob storage [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L221-L233)
- create blob-backed knowledge sources and knowledge bases [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L236-L311)
- provision a searchIndex-backed knowledge source over the existing ACL-stamped index for native ACL-aware retrieval [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L314-L360)

The code comments are explicit that the searchIndex-backed cockpit KB is non-destructive and reversible: it is created alongside the legacy blob KB and points at the same ACL-stamped index. [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L314-L330)

## ACL-sensitive ingest behavior

`collect_pages()` preserves access metadata from manifest `groups` and intentionally distinguishes missing `groups` from an explicit empty list. The code comment says a truthiness check would silently upgrade an explicit "nobody" declaration into the default audience. The same function also rewrites each page body to drop its original generic H1 and replace it with a component-or-platform-qualified title such as `component version — page title`, so retrieved citations carry meaningful source labels rather than opaque page names. [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L168-L218)

`create_knowledge_source()` is intentionally idempotent and skip-if-exists for ACL safety. If the knowledge source already exists, the backend does not recreate it, because `create_or_update_knowledge_source` would regenerate the index schema without the out-of-band `groups` permission field added by ACL setup, and Azure would then reject the attempt to drop that existing field. That means content refresh is expected to happen through upload plus indexer run, not by rebuilding the knowledge source every time. [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L236-L278)

`trigger_indexer()` is explicitly non-blocking by default. It starts a fresh crawl because relying on the indexer's existing schedule can make newly uploaded blobs look ingested when they are not, but it does not wait for full completion unless `wait_s > 0` is requested. The rationale in code is cost and latency: indexing is embedding-bound, the index becomes queryable incrementally, and waiting for large batches would stall callers for 10–20 minutes. [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L69-L105)

`purge_orphans()` is another important operational step: because the indexer does not delete chunks for removed source blobs automatically, the backend reconciles the index against the blob container and deletes orphaned documents. On ACL-enabled indexes it uses `x-ms-enable-elevated-read` so the purge sees all indexed chunks instead of a permission-trimmed zero set. [ingest_docbundles.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/ingest_docbundles.py#L111-L166)

## Backend wiki builder

`wiki_builder.py` is the backend-owned source-grounded generator. It gathers source files, invokes a Foundry model to plan and write wiki pages, validates the generated manifest against the shared docbundle schema, and applies a fidelity gate before writing the final bundle. [wiki_builder.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/wiki_builder.py#L1-L27) [wiki_builder.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/wiki_builder.py#L72-L148)

Two operational details matter for safe changes:

- the gatherer explicitly skips `.worktrees`, caches, and build artifacts so citations stay anchored to canonical source paths [wiki_builder.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/wiki_builder.py#L55-L67) [wiki_builder.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/wiki_builder.py#L150-L161)
- the fidelity gate understands both repo-relative file citations and GitHub blob URLs, strips external URLs, and reads its minimum threshold from `eval/assurance.yaml` [wiki_builder.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/knowledge/wiki_builder.py#L82-L148)

## Contract and freshness assurance

The backend's eval suite contains two bundle-level gates that interact directly with this pipeline:

- `wiki_fidelity_test.py` reuses the same fidelity logic for externally generated bundles and refuses ingest below the configured floor or with worktree citations. [wiki_fidelity_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/wiki_fidelity_test.py#L1-L20) [wiki_fidelity_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/wiki_fidelity_test.py#L59-L101)
- `wiki_freshness_test.py` compares bundle `generatedAt` timestamps with latest git changes in the covered area so stale wiki bundles are detectable. [wiki_freshness_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/wiki_freshness_test.py#L1-L13) [wiki_freshness_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/wiki_freshness_test.py#L26-L88)

`eval.docbundle_contract_test.py` is also part of this subsystem and is especially important for the failure modes around manifest field usage and ACL semantics. Its module docstring says it checks both directions against the contract: fields this repo reads must exist in the schema, fields this repo writes must also exist there, committed bundles must validate, and absent `groups` must remain distinguishable from explicit `groups: []`. That makes it the canonical assurance test for schema drift, manifest field usage, and the absent-versus-empty ACL distinction. [docbundle_contract_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/docbundle_contract_test.py#L1-L28) [docbundle_contract_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/docbundle_contract_test.py#L124-L224)

## Focused validation

- Bundle schema and writer assumptions: `uv run python -m eval.docbundle_contract_test`
- External-bundle fidelity: `uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend`
- Bundle freshness: `uv run python -m eval.wiki_freshness_test`
