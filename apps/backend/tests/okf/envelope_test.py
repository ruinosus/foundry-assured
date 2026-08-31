"""Perfil de autoria: identidade, revisão, estado e metadados OKF preservados."""

from __future__ import annotations

import sys

from app.modules.okf.public import (
    AuthoringInvalid,
    parse_authoring_document,
    serialize_authoring_document,
)

DOCUMENT = """---
type: agent-binding
resource: foundry://agents/ticket-builder/versions/3
title: Ticket builder
status: draft
generated:
  by: process:builder
  at: "2026-08-31T12:00:00Z"
x-foundry-authoring:
  profile_version: "1"
  id: ticket-builder
  revision: "2"
  publication_state: proposed
  tenant: tenant-a
  area: support
  supersedes:
    type: agent-binding
    id: ticket-builder
    revision: "1"
  spec:
    agent:
      name: ticket-builder
      version: 3
---

# Ticket builder

Uses the approved ticket toolbox.
"""

MCP_DOCUMENT = (
    DOCUMENT.replace("type: agent-binding", "type: mcp-binding")
    .replace(
        "resource: foundry://agents/ticket-builder/versions/3",
        "resource: foundry://toolboxes/ticket-tools/versions/4",
    )
    .replace(
        "    agent:\n      name: ticket-builder\n      version: 3",
        "    toolbox:\n      name: ticket-tools\n      version: '4'\n"
        "    tools: [create-ticket]\n"
        "    reviewedSnapshot:\n      id: msnap_ticket\n      hash: '"
        + "a" * 64
        + "'",
    )
)

MIDDLEWARE_DOCUMENT = (
    DOCUMENT.replace("type: agent-binding", "type: middleware-binding")
    .replace(
        "resource: foundry://agents/ticket-builder/versions/3",
        "resource: python://app.modules.tickets/duplicate-ticket-check@1",
    )
    .replace(
        "    agent:\n      name: ticket-builder\n      version: 3",
        "    implementation:\n      name: duplicate-ticket-check\n      version: '1'\n      runtime: agent-framework",
    )
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    document = parse_authoring_document(DOCUMENT)
    check("identity is namespaced and tenant scoped", document.identity == ("tenant-a", "support", "agent-binding", "ticket-builder"))
    check("OKF resource keeps upstream semantics", document.resource == "foundry://agents/ticket-builder/versions/3")
    check("path uses profile identity", str(document.relative_path) == "tenants/tenant-a/areas/support/agent-binding/ticket-builder/2.md")
    check("profile and resource versions stay distinct", document.profile_version == "1" and document.revision == "2")
    check("typed supersedes is preserved", document.supersedes is not None and document.supersedes.revision == "1")
    check("type-specific fields stay in namespaced spec", document.spec["agent"]["version"] == 3)
    check("unknown OKF metadata is preserved", document.okf_metadata["title"] == "Ticket builder")
    check("markdown body remains human-readable", document.body.startswith("# Ticket builder"))
    check("round-trip preserves semantics", parse_authoring_document(serialize_authoring_document(document)) == document)
    check("toolbox binding is versioned", parse_authoring_document(MCP_DOCUMENT).spec["toolbox"]["version"] == "4")
    check("middleware names its runtime", parse_authoring_document(MIDDLEWARE_DOCUMENT).spec["implementation"]["runtime"] == "agent-framework")

    def refuses(name: str, old: str, new: str) -> None:
        try:
            parse_authoring_document(DOCUMENT.replace(old, new), where=name)
        except AuthoringInvalid:
            check(name, True)
        else:
            check(name, False)

    refuses("path traversal in id", "  id: ticket-builder", "  id: ../../secret")
    refuses("unknown authoring type", "type: agent-binding", "type: executable-agent")
    refuses("unknown publication state", "publication_state: proposed", "publication_state: published")
    refuses("unsupported profile version", 'profile_version: "1"', 'profile_version: "2"')
    refuses("tenant path traversal", "tenant: tenant-a", "tenant: ../tenant-b")
    refuses("noncanonical area", "area: support", "area: Support")
    refuses("missing generated provenance", "generated:\n  by: process:builder\n  at: \"2026-08-31T12:00:00Z\"", "generated: null")
    refuses("status cannot diverge from publication", "status: draft", "status: stable")
    refuses("bundle version does not belong on concept", "title: Ticket builder", 'okf_version: "0.2"')
    refuses("supersedes another identity", "    id: ticket-builder\n    revision: \"1\"", "    id: another-agent\n    revision: \"1\"")
    refuses("supersedes current revision", "    revision: \"1\"\n  spec:", "    revision: \"2\"\n  spec:")
    refuses("floating supersedes", "    id: ticket-builder\n    revision: \"1\"", "    id: ticket-builder")
    refuses("unknown reference field", "    revision: \"1\"\n  spec:", "    revision: \"1\"\n    url: https://example.test\n  spec:")
    refuses("empty agent binding", "    agent:\n      name: ticket-builder\n      version: 3", "    agent: {}")

    try:
        parse_authoring_document(
            MCP_DOCUMENT.replace(
                "    toolbox:\n      name: ticket-tools\n      version: '4'",
                "    toolbox:\n      name: ticket-tools\n      version: '4'\n"
                "    endpoint:\n      id: mep_ticket",
            ),
            where="two MCP origins",
        )
    except AuthoringInvalid:
        check("two MCP origins", True)
    else:
        check("two MCP origins", False)

    try:
        parse_authoring_document(
            MCP_DOCUMENT.replace("    tools: [create-ticket]", "    client_secret: plaintext"),
            where="embedded secret",
        )
    except AuthoringInvalid:
        check("embedded secret", True)
    else:
        check("embedded secret", False)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
