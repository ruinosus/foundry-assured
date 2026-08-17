# Knowledge pipeline

The knowledge pipeline is the backend subsystem that turns source or markdown corpora into retrievable knowledge bases with measurable fidelity. It spans generation, adaptation, ingestion, ACL setup, and evaluation gates.

## Generation paths

The README documents two wiki-generation paths for selfwiki: a Foundry pipeline implemented by `wiki_builder.py`, and Microsoft Agent Skills / OpenWiki-driven generation. `wiki_builder.py` itself explains the contract: generate a faithful LLM wiki from real source, paced and bounded, and emit the ingest bundle format that downstream ingestion already understands. Source [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L29-L34)

A key local invariant is that the bundle format is treated as a contract, not a private dialect: manifests are validated against the vendored schema before write. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L14-L27) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L63-L64)

## Fidelity gate

`wiki_builder.py` owns the deterministic fidelity gate. `_fidelity_report` normalizes citations, strips GitHub blob URL prefixes to repo-relative paths, rejects worktree citations, and scores resolved/total citations. `_fidelity_floor()` reads the single source of truth from `eval/assurance.yaml`, where `build.fidelity_min` is `0.80`. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L87-L118) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/wiki_builder.py#L124-L163) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/assurance.yaml#L16-L25)

The separate `eval/wiki_fidelity_test.py` applies that same logic to externally generated bundles so OpenWiki/deepwiki outputs do not bypass the gate. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/wiki_fidelity_test.py#L1-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/wiki_fidelity_test.py#L61-L99)

## OpenWiki adaptation

`adapt_openwiki.py` is the OpenWiki-specific adapter. It reads `openwiki/` output, skips navigation/scaffold files, strips OKF front matter, flattens internal wiki-to-wiki links to text so they do not inflate fidelity, reads `.last-update.json` for documented commit/model, and writes the standard bundle layout. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L1-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L46-L56) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L93-L145) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/adapt_openwiki.py#L158-L212)

The important boundary is that OpenWiki stays a producer; the adapter preserves local ingest and assurance contracts.

## Ingestion and ACL stamping

`ingest_docbundles.py` turns docbundle trees into Azure Blob-backed Search knowledge sources and knowledge bases. `collect_pages()` walks bundle manifests, rewrites titles for meaningful citation labels, and returns both page blobs and component-to-group maps declared by manifests. That group map is then used for ACL stamping, which is how “access follows the source” is enforced. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L58-L66) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L168-L218)

A subtle but important rule appears in `collect_pages()`: absent/null `groups` is not the same as empty `[]`. Missing means “no declaration, let external/default policy decide”; empty means “nobody reads this”, which must stay fail-closed. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/knowledge/internal/ingest_docbundles.py#L194-L201)

## Retrieval assurance

The knowledge pipeline does not end at ingest. Retrieval ACL parity tests prove that the production retrieval code preserves user-specific document visibility all the way through native retrieval and projection logic. That means corpus generation, ACL stamping, and retrieval are one assurance chain, not separate concerns. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L133-L142)

## Focused validation

The narrowest validation commands for knowledge-pipeline changes are:

- `cd apps/backend && uv run python -m eval.wiki_fidelity_test --component <component> --version <version>`
- `cd apps/backend && uv run pytest tests/knowledge`
- `cd apps/backend && uv run pytest eval/docbundle_contract_test.py eval/wiki_fidelity_test.py`

Run those before broader frontend or E2E checks.
