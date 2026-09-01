---
status: accepted
date: 2026-08-31
challenge: 20260831-1229-mcp-binding-discovery
canonical: docs/adr/ADR-033-mcp-discovery-governance-and-drift.md
---

# ADR-033 — MCP discovery is governed evidence, not execution

Decisão estrutural aceita pelo desenvolvedor atuando com autoridade de tech lead/arquiteto em
2026-08-31. O conteúdo, as alternativas e as consequências estão no documento canônico
`docs/adr/ADR-033-mcp-discovery-governance-and-drift.md`.

Escopo aceito: discovery somente por `initialize` + `tools/list`; Foundry como fonte de Toolbox e
connection; egress fail-closed; classificação administrativa tenant-scoped; snapshots sob Azure
Blob WORM/SSE; hash RFC 8785 + SHA-256; drift por tool; e OKF sem credencial ou autoridade.