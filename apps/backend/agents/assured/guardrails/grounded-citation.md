---
# Application data — deliberately NOT AgentSchema.
# AgentSchema has no guardrail concept. A cross-cutting rule wired onto several
# agents is this repository's data (and always was); agents reference it by name
# from metadata["x-foundry-assured"].guardrails and the host renders it as a
# `## Guardrail:` section AFTER the agent's own instructions.
name: grounded-citation
description: Citation duty for KB-grounded answers — cite every claim or say you don't know
severity: error
---
- Cite the source document for every claim you make, by its title.
- If the knowledge base does not contain the answer, say you don't know instead of guessing — never invent runbooks, sources, or steps.
