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

## Where the documents are

The knowledge-base documents are **already retrieved and present in this conversation's
context** — Foundry IQ agentic retrieval injects the relevant Cockpit pages before you
answer. **Read them directly from the context.** This skill has **no document
resources**: do **NOT** call `read_skill_resource` to fetch Cockpit pages or references
(there are none here, and guessing page names will fail). Answer a clear question
straight from the retrieved documents — never reply asking the user to "be more
specific" when the documents to answer are already in context.

## Procedure

1. Detect the language of the question and answer in the **same language** (pt-BR for
   Cockpit questions).
2. Use **ONLY** the retrieved knowledge-base documents (already in context) as evidence.
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
