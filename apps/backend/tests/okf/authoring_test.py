"""Permissões declarativas dentro do perfil de autoria do copiloto."""

from __future__ import annotations

import sys

from app.modules.okf.public import (
    AuthoringInvalid,
    copilot_allows,
    parse_authoring_document,
)

DOCUMENT = """---
type: copilot
status: draft
generated:
  by: process:builder
  at: "2026-08-31T12:00:00Z"
x-foundry-authoring:
  profile_version: "1"
  id: ticket-builder
  revision: "1"
  publication_state: proposed
  tenant: tenant-a
  area: support
  spec:
    writes:
      - type: usecase
        operations: [create, revise]
      - type: policy
        operations: [revise]
    cannotWrite:
      - type: usecase
      - type: policy
      - type: connection
      - type: middleware-implementation
      - type: tenant-config
---

# Ticket builder
"""


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    document = parse_authoring_document(DOCUMENT)
    check("cannotWrite overrides writes", not copilot_allows(document, "usecase", "create"))
    check("policy is never authorable", not copilot_allows(document, "policy", "revise"))
    check("missing grant is denied", not copilot_allows(document, "agent-binding", "create"))
    check("unknown operation is denied", not copilot_allows(document, "usecase", "publish"))

    allowed = parse_authoring_document(DOCUMENT.replace("      - type: usecase\n      - type: policy", "      - type: policy"))
    check("declared operation is allowed", copilot_allows(allowed, "usecase", "create"))
    check("undeclared operation is denied", not copilot_allows(allowed, "usecase", "deprecate"))

    def refuses(name: str, old: str, new: str) -> None:
        try:
            parse_authoring_document(DOCUMENT.replace(old, new), where=name)
        except AuthoringInvalid:
            check(name, True)
        else:
            check(name, False)

    refuses("unknown operation fails schema", "operations: [create, revise]", "operations: [create, publish]")
    refuses("cannotWrite cannot carry operations", "      - type: connection", "      - {type: connection, operations: [create]}")
    refuses(
        "duplicate write rule is ambiguous",
        "      - type: policy\n        operations: [revise]",
        "      - type: usecase\n        operations: [revise]",
    )

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
