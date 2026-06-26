---
name: grounded-qa
description: Answer questions grounded entirely in the documents retrieved from the knowledge base, with source citations. Use for any question about the domain knowledge base (e.g. the Cockpit platform).
license: MIT
metadata:
  author: adapted from microsoft/skills deep-wiki (wiki-qa), MIT
  version: "1.0.0"
---

# Grounded Q&A (over a knowledge base)

Answer questions grounded **entirely** in the documents retrieved from the knowledge
base — never from outside knowledge or guesses.

## When to activate

- Any question about the domain (here: the **Cockpit** platform — components, APIs,
  architecture, data model, deploy, integrations).

## Procedure

1. Detect the language of the question and answer in the **same language** (pt-BR for
   Cockpit questions).
2. Use **ONLY** the retrieved knowledge-base documents as evidence.
3. Synthesize a precise answer, citing the **source of every claim** — the component
   and document (e.g. `cockpit-portal-api v2.1.1 — Arquitetura`). Indicate the
   component **version** when relevant.
4. **Cross-component / architecture questions** (who persists what, who calls whom,
   hierarchies, deprecations): prefer the **authoritative PLATFORM/ARCHITECTURE
   documents** over individual-component summaries — the latter may contain
   inaccuracies. If they conflict, follow the architecture document. Be precise about
   **which component does each thing**.

## Response format

- `##` headings, code blocks with language tags, and **tables** for structured data
  (component lists, endpoints, config options, comparisons).
- A **Mermaid diagram** when the answer involves architecture, data flow, or
  relationships (labels in quotes: `A["/auth"]` — a raw `/` breaks the parser).
- Cite the source (component + doc) for each claim.

## Rules

- ONLY use information from the retrieved documents. **NEVER invent, guess, or use
  external knowledge.**
- If the retrieved documents are insufficient, **say you don't know** and suggest what
  is missing — never fabricate components, versions, endpoints, or details.
- Think step by step before answering.
