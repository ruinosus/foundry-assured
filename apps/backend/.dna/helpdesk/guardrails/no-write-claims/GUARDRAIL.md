---
name: no-write-claims
description: HITL write safety — state changes belong to the approval step, never to the agent's own claims
severity: error
scope: output
---

- For any action that changes state (deploy, create issue, directory change), explain what you would do and let the approval step handle it — never claim you performed a write.
