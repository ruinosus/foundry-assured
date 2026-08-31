"""F06: drift é estável, seletivo por tool e bloqueia promoção de versão."""

from __future__ import annotations

import sys

from app.modules.platform_ops.public import compare_mcp_snapshots


def _snapshot(version: str, tools: list[tuple[str, str]]) -> dict:
    return {
        "source": {
            "kind": "toolbox",
            "id": "tb-1",
            "resolvedVersion": version,
        },
        "tools": [
            {"name": name, "contractHash": contract_hash}
            for name, contract_hash in tools
        ],
    }


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    previous = _snapshot(
        "2",
        [
            ("changed", "a" * 64),
            ("classification", "b" * 64),
            ("removed", "c" * 64),
            ("stable", "d" * 64),
        ],
    )
    current = _snapshot(
        "2",
        [
            ("stable", "d" * 64),
            ("added", "e" * 64),
            ("classification", "b" * 64),
            ("changed", "f" * 64),
        ],
    )
    result = compare_mcp_snapshots(
        previous,
        current,
        reviewed_classifications={"classification": "read", "stable": "read"},
        current_classifications={"classification": "write", "stable": "read"},
    )
    changes = {item["name"]: item["changes"] for item in result["tools"]}
    check("adição aparece no diff", changes["added"] == ["added"])
    check("remoção aparece no diff", changes["removed"] == ["removed"])
    check("contrato aparece no diff", changes["changed"] == ["contract"])
    check(
        "classificação aparece no diff",
        changes["classification"] == ["classification"],
    )
    check("tool inalterada não aparece", "stable" not in changes)
    check(
        "somente tools afetadas ficam em quarentena",
        result["quarantinedTools"]
        == ["added", "changed", "classification", "removed"],
    )
    check("drift por tool bloqueia promoção", result["blocking"] is True)
    check("mesma versão não exige review completo", result["versionChanged"] is False)

    previous_pairs = [
        (item["name"], item["contractHash"]) for item in previous["tools"]
    ]
    version_drift = compare_mcp_snapshots(previous, _snapshot("3", previous_pairs))
    check("mudança de versão é detectada", version_drift["versionChanged"] is True)
    check("mudança de versão bloqueia promoção", version_drift["blocking"] is True)
    check("mudança de versão exige review completo", version_drift["requiresFullReview"] is True)

    reordered = _snapshot("2", list(reversed(previous_pairs)))
    no_drift = compare_mcp_snapshots(previous, reordered)
    check("ordem de tools não gera drift", no_drift["blocking"] is False)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
