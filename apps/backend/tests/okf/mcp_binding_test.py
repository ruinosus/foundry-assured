"""F02: contrato estrito do documento mcp-binding."""

from __future__ import annotations

import sys
from typing import Any

import yaml

from app.modules.okf.public import AuthoringInvalid, parse_authoring_document


def _document(spec: dict[str, Any]) -> str:
    header = {
        "type": "mcp-binding",
        "status": "draft",
        "generated": {"by": "process:mcp-binding-test", "at": "2026-08-31T12:00:00Z"},
        "x-foundry-authoring": {
            "profile_version": "1",
            "id": "platform-mcp",
            "revision": "1",
            "publication_state": "proposed",
            "tenant": "tenant-a",
            "area": "platform",
            "spec": spec,
        },
    }
    return f"---\n{yaml.safe_dump(header, sort_keys=False).rstrip()}\n---\n\n# MCP binding\n"


def _valid(**overrides: Any) -> dict[str, Any]:
    spec = {
        "toolbox": {"name": "platform-tools", "version": "3"},
        "tools": ["search_resources", "update_resource"],
        "reviewedSnapshot": {"id": "msnap_reviewed", "hash": "a" * 64},
    }
    spec.update(overrides)
    return {key: value for key, value in spec.items() if value is not None}


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    def accepts(name: str, spec: dict[str, Any]) -> None:
        try:
            parse_authoring_document(_document(spec), where=name)
        except AuthoringInvalid:
            check(name, False)
        else:
            check(name, True)

    def refuses(name: str, spec: dict[str, Any]) -> None:
        try:
            parse_authoring_document(_document(spec), where=name)
        except AuthoringInvalid:
            check(name, True)
        else:
            check(name, False)

    accepts("fixed Toolbox version", _valid())
    accepts(
        "default Toolbox version",
        _valid(toolbox={"name": "platform-tools", "useDefault": True}),
    )
    accepts(
        "approved endpoint reference",
        _valid(endpoint={"id": "mep_approved"}, toolbox=None),
    )

    refuses("exactly one source is required", {key: value for key, value in _valid().items() if key != "toolbox"})
    refuses("two sources are ambiguous", _valid(endpoint={"id": "mep_approved"}))
    refuses(
        "Toolbox version and default are exclusive",
        _valid(toolbox={"name": "platform-tools", "version": "3", "useDefault": True}),
    )
    refuses("useDefault must be true", _valid(toolbox={"name": "platform-tools", "useDefault": False}))
    refuses("tools cannot be empty", _valid(tools=[]))
    refuses("tools must be unique", _valid(tools=["search_resources", "search_resources"]))
    refuses(
        "snapshot hash must be lowercase SHA-256",
        _valid(reviewedSnapshot={"id": "msnap_reviewed", "hash": "A" * 64}),
    )
    refuses("unknown fields fail", _valid(executable=True))
    refuses("classification was removed", _valid(classification=[]))
    refuses("connection was removed", _valid(toolbox={"name": "platform-tools", "version": "3", "connection": "ops"}))
    refuses("URL was removed", _valid(endpoint={"id": "mep_approved", "url": "https://example.test"}, toolbox=None))
    refuses("recursive secret-like keys fail", _valid(metadata={"nested": [{"clientSecret": "canary"}]}))

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
