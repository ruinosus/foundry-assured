"""Resolução do perfil de autoria e imutabilidade de revisões conhecidas."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, replace

from app.modules.okf.public import (
    AuthoringCatalog,
    AuthoringInvalid,
    parse_authoring_document,
)
from tests.okf.envelope_test import DOCUMENT, MCP_DOCUMENT


def _agent(*, versioned: bool = True, publication_state: str = "proposed"):
    reference_revision = "\n        revision: \"2\"" if versioned else ""
    status = "stable" if publication_state == "active" else "draft"
    text = (
        DOCUMENT.replace("status: draft", f"status: {status}")
        .replace("publication_state: proposed", f"publication_state: {publication_state}")
        .replace(
            "  supersedes:\n    type: agent-binding\n    id: ticket-builder\n    revision: \"1\"\n",
            "",
        )
        .replace(
            "  spec:\n    agent:",
            "  spec:\n    requires:\n      - type: mcp-binding\n        id: ticket-builder"
            f"{reference_revision}\n    agent:",
        )
    )
    return parse_authoring_document(text)


def _mcp(*, tenant: str = "tenant-a", revision: str = "2", publication_state: str = "active"):
    status = "stable" if publication_state == "active" else "draft"
    return parse_authoring_document(
        MCP_DOCUMENT.replace("status: draft", f"status: {status}")
        .replace("  tenant: tenant-a", f"  tenant: {tenant}")
        .replace("  revision: \"2\"", f"  revision: \"{revision}\"", 1)
        .replace("  publication_state: proposed", f"  publication_state: {publication_state}")
        .replace(
            "  supersedes:\n    type: mcp-binding\n    id: ticket-builder\n    revision: \"1\"\n",
            "",
        )
    )


def main() -> int:
    failures: list[str] = []

    def check(name: str, operation, *, fails: bool = False) -> None:
        try:
            operation()
        except (AuthoringInvalid, FrozenInstanceError, TypeError):
            passed = fails
        else:
            passed = not fails
        print(f"  {'✓' if passed else '✗'} {name}")
        if not passed:
            failures.append(name)

    check("versioned reference resolves", lambda: AuthoringCatalog([_agent(), _mcp()]))
    check("missing reference fails", lambda: AuthoringCatalog([_agent()]), fails=True)
    check("reference cannot cross tenant", lambda: AuthoringCatalog([_agent(), _mcp(tenant="tenant-b")]), fails=True)
    check("floating reference resolves unique active", lambda: AuthoringCatalog([_agent(versioned=False), _mcp()]))
    check(
        "active document cannot keep floating reference",
        lambda: AuthoringCatalog([_agent(versioned=False, publication_state="active"), _mcp()]),
        fails=True,
    )
    check("published revision cannot be overwritten", lambda: AuthoringCatalog([_mcp(), _mcp()]), fails=True)
    check(
        "identity has at most one active revision",
        lambda: AuthoringCatalog([_mcp(), _mcp(revision="3")]),
        fails=True,
    )

    published = _mcp()
    AuthoringCatalog([published])
    original_name = published.spec["toolbox"]["name"]

    def mutate_published_mapping() -> None:
        published.spec["toolbox"]["name"] = "changed-after-validation"

    def mutate_published_list() -> None:
        published.spec["tools"] = []

    def bypass_mapping_override() -> None:
        dict.__setitem__(published.spec, "secret", "after-validation")

    def bypass_list_override() -> None:
        list.append(published.spec["tools"], "late")

    check("published nested mappings are immutable", mutate_published_mapping, fails=True)
    check("published top-level mappings are immutable", mutate_published_list, fails=True)
    check("dict descriptor cannot bypass immutability", bypass_mapping_override, fails=True)
    check("list descriptor cannot bypass immutability", bypass_list_override, fails=True)
    check(
        "catalog retains validated content",
        lambda: original_name == published.spec["toolbox"]["name"],
    )

    immutable_catalog = AuthoringCatalog([published])

    def mutate_catalog_index() -> None:
        immutable_catalog._documents[(*published.identity, published.revision)] = _agent()

    def replace_catalog_index() -> None:
        immutable_catalog._documents = {}

    invalid_direct = replace(
        published,
        status="draft",
        spec={"toolbox": {"name": "ticket-tools", "version": "4", "connection": "service-now", "client_secret": "late"}},
    )
    check("catalog index is immutable", mutate_catalog_index, fails=True)
    check("catalog index cannot be reassigned", replace_catalog_index, fails=True)
    check(
        "directly constructed documents are revalidated",
        lambda: AuthoringCatalog([invalid_direct]),
        fails=True,
    )

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
