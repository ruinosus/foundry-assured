---
type: backend-knowledge-pipeline
title: Knowledge pipeline
description: Backend pipeline for corpus ingest, docbundle adaptation, ACL stamping, generated wiki ingestion, and schema validation for grounded knowledge bases.
tags: [backend, knowledge, ingestion, wiki]
---

# Knowledge pipeline

<!-- openwiki: broken internal link [../../apps/backend/app/knowledge] file "../../apps/backend/app/knowledge" does not exist. Fix the href or restore the target, then delete this comment. -->
The backend knowledge pipeline is the bridge between source materials and grounded runtime behavior. It is implemented under [`apps/backend/app/knowledge`](../../apps/backend/app/knowledge).

This subsystem is responsible for turning:

- curated corpus documents,
- docbundle-format content,
- generated wiki output,
- and ACL metadata

into assets that the grounded domains and assurance mechanisms can rely on.

## Main modules

| Module | Purpose |
| --- | --- |
| `ingest.py` | Ingest the base corpus and knowledge-base resources. |
| `ingest_docbundles.py` | Ingest docbundle-format corpora into search-backed assets. |
| `adapt_openwiki.py` | Convert generated OpenWiki output into ingestable docbundles. |
| `adapt_deepwiki.py` | Convert deepwiki-style output into the same internal format. |
| `wiki_builder.py` | Generate a repository wiki using Foundry models and fidelity gates. |
| `acl_setup.py` | Apply ACL-related setup for searchable corpora. |
| `docbundle_schema.py` and `docbundle.schema.json` | Validate the repository's vendored docbundle contract. |
| `skills/*` | IDE-agent skills for wiki generation. |

## Sources of knowledge

The repository uses more than one input source for grounded domains:

### Helpdesk corpus

`app/knowledge/corpus/` contains the helpdesk runbook material used by the workflow retrieve step and related KB provisioning.

### Cockpit docbundles

Cockpit uses docbundle ingestion and ACL-aware search-backed KBs. Its searchIndex-backed configuration appears in `TenantConfig` and backend domain rows.

### Selfwiki generated corpus

Selfwiki uses generated wiki output about this repository. The README and code document two generation paths:

- Foundry-based wiki builder in `wiki_builder.py`
- IDE-agent skill-based generation under `app/knowledge/skills/`

The output can then be adapted into docbundles and ingested into the selfwiki corpus and KB/index.

## OpenWiki adaptation

`adapt_openwiki.py` is part of the repository's automation loop. The GitHub workflow `wiki-regen.yml` runs:

1. OpenWiki generation into `/openwiki`,
2. adaptation into `docs/wiki`,
3. fidelity gating,
4. pull request creation.

That means generated wiki output is not just documentation. It is also a knowledge artifact consumed by the product's selfwiki domain.

## Docbundle contract

The repository treats docbundle format as an external contract rather than a local invention.

Evidence:

- `pyproject.toml` includes `jsonschema` specifically to validate doc-bundle manifests against the vendored contract.
- `apps/backend/eval/docbundle_contract_test.py` checks that every manifest field the code reads or writes exists in the schema.
- `apps/backend/eval/README.md` explains the historical anti-fork reason for this guard.

The practical rule is: if you change how manifests are produced or consumed, update the vendored schema and contract tests rather than slipping in ad hoc fields.

## ACL stamping relationship

Grounded ACL behavior depends on knowledge assets being stamped correctly. This is why the knowledge pipeline and retrieval pipeline are linked:

- the knowledge pipeline prepares ACL-bearing corpora and indexes,
- the retrieval pipeline sends end-user identity for trimming,
- security tests assert parity and leak resistance across both.

For cockpit in particular, tests like `cockpit_acl_stamp_test.py` protect assumptions that begin in ingest and end in runtime search behavior.

## Wiki builder

`wiki_builder.py` is the repository's Foundry-model path for generating a repo wiki. The README describes it as:

- automated via `uv run`,
- using a Foundry model such as `gpt-5-mini`,
- guarded by a build-fidelity gate.

This builder is part of the larger assurance story: generated knowledge must be measured before it becomes part of the grounding corpus.

## IDE skills path

The `app/knowledge/skills` directory contains `wiki-architect` and `wiki-page-writer` skills used by IDE agents. The README positions this as the zero-cloud, no-azd path for creating wiki content from the repository.

This is a second producer path for the same general knowledge artifact. The adaptation and fidelity layers are what keep the product from depending on one specific generator implementation.

## Relationship to runtime domains

- `helpdesk` depends on provisioned helpdesk corpus and KB.
- `cockpit` depends on cockpit docbundles and ACL-aware searchIndex KBs.
- `selfwiki` depends on generated wiki output adapted and ingested into the selfwiki corpus.

So when a grounded domain misbehaves, the bug may live in retrieval, prompting, or the upstream knowledge pipeline.

## Focused tests

The most important knowledge-pipeline tests are:

- `docbundle_contract_test.py`: schema and producer/consumer contract integrity.
- `wiki_fidelity_test.py`: generated wiki citation fidelity.
- `wiki_freshness_test.py`: drift detection for stale wiki areas.
- `cockpit_acl_stamp_test.py`: ACL-stamped corpus assumptions.
- `native_snippet_test.py` and retrieval tests indirectly validate ingested field availability.

## Validation

From `apps/backend/`:

```bash
uv run pytest eval/docbundle_contract_test.py eval/wiki_fidelity_test.py eval/wiki_freshness_test.py eval/cockpit_acl_stamp_test.py
```

## Related pages

- [Grounded domains](grounded-domains.md)
- [Retrieval and ACL](retrieval-and-acl.md)
- [Security and fidelity gates](../assurance/security-and-fidelity-gates.md)
- [Automation and release](../operations/automation-and-release.md)
