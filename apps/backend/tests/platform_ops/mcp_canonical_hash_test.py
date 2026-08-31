"""F06: hash canônico cobre somente o contrato MCP sanitizado."""

from __future__ import annotations

import sys

from app.modules.platform_ops.public import canonical_tool_hash


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    contract = {
        "name": "query",
        "description": "Consulta segura",
        "inputSchema": {
            "type": "object",
            "required": ["query", "scope"],
            "properties": {
                "query": {"type": "string"},
                "scope": {"type": "string"},
            },
        },
        "outputSchema": {"type": "object"},
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "unknown": "discarded",
        },
        "_meta": {"token": "must-not-enter-hash"},
    }
    reordered = {
        "annotations": {
            "unknown": "changed-but-discarded",
            "destructiveHint": False,
            "readOnlyHint": True,
        },
        "outputSchema": {"type": "object"},
        "inputSchema": {
            "properties": {
                "scope": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["query", "scope"],
            "type": "object",
        },
        "description": "Consulta segura",
        "name": "query",
    }
    baseline = canonical_tool_hash(contract)
    check("hash SHA-256 hexadecimal", len(baseline) == 64)
    check("ordem de chaves e campos descartados não importam", baseline == canonical_tool_hash(reordered))

    changed_description = {**reordered, "description": "Outra instrução"}
    check("descrição participa do hash", baseline != canonical_tool_hash(changed_description))
    changed_schema = {
        **reordered,
        "inputSchema": {**reordered["inputSchema"], "additionalProperties": False},
    }
    check("schemas participam do hash", baseline != canonical_tool_hash(changed_schema))
    changed_annotation = {
        **reordered,
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    }
    check("annotations permitidas participam do hash", baseline != canonical_tool_hash(changed_annotation))
    changed_array = {
        **reordered,
        "inputSchema": {
            **reordered["inputSchema"],
            "required": ["scope", "query"],
        },
    }
    check("ordem semântica de arrays é preservada", baseline != canonical_tool_hash(changed_array))

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
