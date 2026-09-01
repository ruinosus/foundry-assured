"""Conformidade por tipo do perfil de autoria e vertical de tickets."""

from __future__ import annotations

import sys
from typing import Any

import yaml

from app.modules.okf.public import (
    AuthoringCatalog,
    AuthoringInvalid,
    parse_authoring_document,
)


def _document(doc_type: str, identifier: str, spec: dict[str, Any]) -> str:
    header = {
        "type": doc_type,
        "status": "stable",
        "generated": {"by": "process:schema-test", "at": "2026-08-31T12:00:00Z"},
        "x-foundry-authoring": {
            "profile_version": "1",
            "id": identifier,
            "revision": "1",
            "publication_state": "active",
            "tenant": "tenant-a",
            "area": "support",
            "spec": spec,
        },
    }
    return f"---\n{yaml.safe_dump(header, sort_keys=False).rstrip()}\n---\n\n# {identifier}\n"


SPECS: dict[str, dict[str, Any]] = {
    "copilot": {
        "writes": [{"type": "usecase", "operations": ["create", "revise"]}],
        "cannotWrite": [{"type": "policy"}],
    },
    "usecase": {
        "requires": [
            {"type": "agent-binding", "id": "ticket-agent", "revision": "1"},
            {"type": "mcp-binding", "id": "ticket-mcp", "revision": "1"},
            {"type": "middleware-binding", "id": "ticket-dedup", "revision": "1"},
        ],
        "targets": [{"type": "adapter-binding", "id": "ticket-adapter", "revision": "1"}],
        "approval": {"required": True, "role": "Approver"},
        "cost": {"kind": "unknown"},
        "citation": "required",
        "gaps": [],
    },
    "formflow": {
        "sections": [{"id": "identity", "fields": [{"id": "name", "type": "text"}]}],
        "review": [],
        "plan": [],
    },
    "policy": {
        "enforcement": "external",
        "sources": ["entra-app-roles", "foundry-tool-approval"],
    },
    "agent-binding": {
        "agent": {"name": "ticket-agent", "version": "1"},
        "authoringRoute": "prompt",
    },
    "mcp-binding": {
        "toolbox": {"name": "ticket-tools", "version": "1"},
        "tools": ["create-ticket"],
        "reviewedSnapshot": {"id": "msnap_ticket", "hash": "a" * 64},
    },
    "middleware-binding": {
        "implementation": {"name": "duplicate-ticket-check", "version": "1", "runtime": "agent-framework"}
    },
    "adapter-binding": {
        "adapter": {"name": "service-now", "version": "1", "runtime": "backend"},
        "connection": "service-now",
        "requires": [],
    },
    "bundle": {
        "includes": [{"type": "usecase", "id": "ticket-create", "revision": "1"}]
    },
    "log": {
        "events": [{"at": "2026-08-31T12:00:00Z", "by": "human:user-a", "action": "published", "revision": "1"}]
    },
}

IDENTIFIERS = {
    "copilot": "ticket-copilot",
    "usecase": "ticket-create",
    "formflow": "ticket-form",
    "policy": "ticket-policy",
    "agent-binding": "ticket-agent",
    "mcp-binding": "ticket-mcp",
    "middleware-binding": "ticket-dedup",
    "adapter-binding": "ticket-adapter",
    "bundle": "ticket-bundle",
    "log": "ticket-log",
}


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    documents = []
    for doc_type, spec in SPECS.items():
        document = parse_authoring_document(_document(doc_type, IDENTIFIERS[doc_type], spec))
        documents.append(document)
        check(f"{doc_type} has a registered schema", document.type == doc_type)

    catalog = AuthoringCatalog(documents)
    usecase = next(document for document in documents if document.type == "usecase")
    resolved = catalog.resolved_references(usecase)
    check("ticket fixture resolves all required components", len(resolved) == 4)
    check("ticket requires approval and citation", usecase.spec["approval"]["required"] and usecase.spec["citation"] == "required")

    def refuses(name: str, doc_type: str, spec: dict[str, Any]) -> None:
        try:
            parse_authoring_document(_document(doc_type, "invalid", spec), where=name)
        except AuthoringInvalid:
            check(name, True)
        else:
            check(name, False)

    refuses("policy cannot claim local enforcement", "policy", {"enforcement": "local", "sources": ["code"]})
    refuses("usecase approval requires a role", "usecase", {**SPECS["usecase"], "approval": {"required": True}})
    refuses(
        "known cost requires currency",
        "usecase",
        {**SPECS["usecase"], "cost": {"kind": "known", "estimate": 10}},
    )
    refuses(
        "formflow rejects untyped fields",
        "formflow",
        {"sections": [{"id": "identity", "executable": True, "fields": [{}]}], "review": [], "plan": []},
    )
    refuses("MCP classification is not document authority", "mcp-binding", {**SPECS["mcp-binding"], "classification": []})
    refuses(
        "agent binding rejects unknown authoring route",
        "agent-binding",
        {**SPECS["agent-binding"], "authoringRoute": "custom-runtime"},
    )
    for route in ("prompt", "workflow", "container"):
        reference = (
            f"registry.example/{route}-agent@sha256:{'a' * 64}"
            if route == "container"
            else "definitions/agent.yaml"
        )
        routed = _document(
            "agent-binding",
            f"{route}-agent",
            {**SPECS["agent-binding"], "authoringRoute": route},
        ).replace("type: agent-binding", f"type: agent-binding\nresource: {route}:{reference}")
        check(f"agent binding accepts {route} resource", lambda routed=routed: parse_authoring_document(routed))
    refuses_document = _document(
        "agent-binding",
        "wrong-route",
        {**SPECS["agent-binding"], "authoringRoute": "prompt"},
    ).replace("type: agent-binding", "type: agent-binding\nresource: container:definitions/agent.yaml")
    try:
        parse_authoring_document(refuses_document)
    except AuthoringInvalid:
        check("agent binding rejects resource from another route", True)
    else:
        check("agent binding rejects resource from another route", False)
    refuses("adapter stores connection reference only", "adapter-binding", {**SPECS["adapter-binding"], "client_secret": "plain"})
    refuses("bundle reference type must exist", "bundle", {"includes": [{"type": "agent", "id": "invented", "revision": "1"}]})

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
