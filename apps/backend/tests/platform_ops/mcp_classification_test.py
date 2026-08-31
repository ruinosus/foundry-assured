"""F05: classificação Admin é tenant-safe, auditável e fail-closed."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.modules.platform_ops.public import (
    ClassificationConflict,
    ClassificationInvalid,
    InMemoryClassificationStore,
    classify_mcp_tool,
    derive_runtime_config,
    effective_tool_state,
)
from app.modules.tenancy.public import set_current_tenant

SNAPSHOT = {
    "snapshotId": "msnap_f05",
    "tenantKey": "tenant-a",
    "source": {"kind": "endpoint", "id": "mep_source"},
    "tools": [
        {
            "name": "query",
            "contractHash": "a" * 64,
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "mutate",
            "contractHash": "b" * 64,
            "annotations": {"readOnlyHint": False, "destructiveHint": True},
        },
    ],
}


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    store = InMemoryClassificationStore()
    audits: list[dict] = []
    snapshot_reader = lambda _id: SNAPSHOT
    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    try:
        first = classify_mcp_tool(
            "msnap_f05",
            "query",
            effect="read",
            reason="consulta verificada",
            expected_revision=0,
            store=store,
            snapshot_reader=snapshot_reader,
            audit_recorder=lambda **event: audits.append(event) or {"hash": "audit"},
            actor="human:admin",
        )
        check("primeira decisão cria revisão 1", first["revision"] == 1)
        check("read confiável fica read", first["effectiveEffect"] == "read")
        read_runtime = derive_runtime_config(
            SNAPSHOT, ["query"], store=store
        )
        check("read entra na allowlist", read_runtime["allowedTools"] == ["query"])
        check(
            "read nunca exige aprovação",
            read_runtime["approvalMode"]["never_require_approval"] == ["query"],
        )

        second = classify_mcp_tool(
            "msnap_f05",
            "query",
            effect="write",
            reason="revisão conservadora",
            expected_revision=1,
            store=store,
            snapshot_reader=snapshot_reader,
            audit_recorder=lambda **event: audits.append(event) or {"hash": "audit"},
            actor="human:admin",
        )
        check("update CAS incrementa revisão", second["revision"] == 2)
        check(
            "write sempre exige aprovação",
            second["effectiveEffect"] == "write_requires_approval",
        )
        try:
            classify_mcp_tool(
                "msnap_f05",
                "query",
                effect="read",
                reason="stale",
                expected_revision=1,
                store=store,
                snapshot_reader=snapshot_reader,
                audit_recorder=lambda **event: audits.append(event) or {"hash": "audit"},
            )
        except ClassificationConflict:
            check("revisão stale conflita", True)
        else:
            check("revisão stale conflita", False)

        elevated = classify_mcp_tool(
            "msnap_f05",
            "mutate",
            effect="read",
            reason="servidor declarou mutação",
            expected_revision=0,
            store=store,
            snapshot_reader=snapshot_reader,
            audit_recorder=lambda **event: audits.append(event) or {"hash": "audit"},
            actor="human:admin",
        )
        check(
            "metadata remota só eleva risco",
            elevated["effectiveEffect"] == "write_requires_approval",
        )
        check("decisões e conflito são auditados", len(audits) == 5)
        check(
            "audit não persiste metadata remota",
            all("annotations" not in str(event) for event in audits),
        )
        check(
            "chave inclui source, tool e hash",
            store.get("tenant-a", "mep_source", "query", "a" * 64) is not None,
        )
        audit_failed_store = InMemoryClassificationStore()
        try:
            classify_mcp_tool(
                "msnap_f05",
                "query",
                effect="read",
                reason="evidence indisponível",
                expected_revision=0,
                store=audit_failed_store,
                snapshot_reader=snapshot_reader,
                audit_recorder=lambda **_event: (_ for _ in ()).throw(
                    RuntimeError("audit unavailable")
                ),
            )
        except RuntimeError:
            check(
                "falha de audit impede persistência",
                audit_failed_store.get(
                    "tenant-a", "mep_source", "query", "a" * 64
                )
                is None,
            )
        else:
            check("falha de audit impede persistência", False)

        missing = effective_tool_state(None, {"readOnlyHint": True})
        check("sem decisão fica quarantined", missing["effect"] == "quarantined")
        forbidden = effective_tool_state(
            store.get("tenant-a", "mep_source", "query", "a" * 64),
            {"readOnlyHint": True},
            permitted=False,
        )
        check("policy ou RBAC pode proibir", forbidden["effect"] == "forbidden")
        stale = effective_tool_state(
            store.get("tenant-a", "mep_source", "query", "a" * 64),
            {"readOnlyHint": True},
            current=False,
        )
        check("snapshot stale volta à quarentena", stale["effect"] == "quarantined")
        runtime = derive_runtime_config(SNAPSHOT, ["query", "mutate"], store=store)
        check(
            "writes conformes entram na allowlist",
            runtime["allowedTools"] == ["query", "mutate"],
        )
        check(
            "writes usam aprovação nativa obrigatória",
            runtime["approvalMode"]["always_require_approval"]
            == ["query", "mutate"],
        )
        blocked_runtime = derive_runtime_config(
            SNAPSHOT,
            ["query", "mutate"],
            store=store,
            permitted=lambda name: name != "mutate",
        )
        check(
            "policy remove sem reduzir risco",
            blocked_runtime["allowedTools"] == ["query"],
        )

        set_current_tenant(SimpleNamespace(tid="tenant-b"))
        check(
            "decisão não cruza tenant",
            store.get("tenant-b", "mep_source", "query", "a" * 64) is None,
        )

        set_current_tenant(SimpleNamespace(tid="tenant-a"))
        try:
            classify_mcp_tool(
                "msnap_f05",
                "query",
                effect="execute",
                reason="inválido",
                expected_revision=2,
                store=store,
                snapshot_reader=snapshot_reader,
            )
        except ClassificationInvalid:
            check("effect inválido é rejeitado", True)
        else:
            check("effect inválido é rejeitado", False)
    finally:
        set_current_tenant(None)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
