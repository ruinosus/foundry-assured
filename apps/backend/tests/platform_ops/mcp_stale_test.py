"""F06: review promove snapshot completo e falha operacional marca stale."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from app.modules.platform_ops.public import (
    InMemoryMcpSourceStore,
    SnapshotReviewInvalid,
    discover_toolbox,
    get_mcp_source,
    observe_mcp_snapshot,
    review_mcp_snapshot,
    source_tool_is_current,
)
from app.modules.tenancy.public import set_current_tenant


def _snapshot(snapshot_id: str, contract_hash: str = "a" * 64) -> dict:
    return {
        "snapshotId": snapshot_id,
        "snapshotHash": contract_hash,
        "tenantKey": "tenant-a",
        "source": {
            "kind": "toolbox",
            "id": "tb-1",
            "resolvedVersion": "2",
        },
        "observedAt": "2026-08-31T20:00:00+00:00",
        "tools": [
            {"name": "query", "contractHash": contract_hash},
            {"name": "stable", "contractHash": "b" * 64},
        ],
    }


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    store = InMemoryMcpSourceStore()
    evidence = {"msnap_1": _snapshot("msnap_1")}
    audits: list[dict] = []
    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    try:
        observed = observe_mcp_snapshot(evidence["msnap_1"], store=store)
        check("primeira observação exige review", observed["drift"]["blocking"] is True)
        try:
            review_mcp_snapshot(
                "msnap_1",
                reason="revisão incompleta",
                expected_revision=1,
                store=store,
                snapshot_reader=evidence.get,
                classification_reader=lambda _snapshot: {},
                audit_recorder=lambda **event: audits.append(event),
            )
        except SnapshotReviewInvalid:
            check("review exige classificação completa", True)
        else:
            check("review exige classificação completa", False)

        reviewed = review_mcp_snapshot(
            "msnap_1",
            reason="contrato e classificação revisados",
            expected_revision=1,
            store=store,
            snapshot_reader=evidence.get,
            classification_reader=lambda _snapshot: {
                "query": "read",
                "stable": "read",
            },
            audit_recorder=lambda **event: audits.append(event),
            actor="human:admin",
        )
        check("review promove snapshot", reviewed["reviewedSnapshotId"] == "msnap_1")
        check("review limpa drift", reviewed["drift"] is None)
        check("review é auditado separadamente", len(audits) == 1)

        evidence["msnap_2"] = _snapshot("msnap_2", "c" * 64)
        drifted = observe_mcp_snapshot(
            evidence["msnap_2"],
            store=store,
            snapshot_reader=evidence.get,
            classification_reader=lambda _snapshot: {
                "query": "read",
                "stable": "read",
            },
        )
        check(
            "nova observação detecta somente contrato alterado",
            drifted["drift"]["quarantinedTools"] == ["query"],
        )
        check(
            "tool alterada é bloqueada antes da rede",
            source_tool_is_current(
                "msnap_2", "query", source_id="tb-1", store=store
            )
            is False,
        )
        check(
            "tool inalterada permanece corrente",
            source_tool_is_current(
                "msnap_2", "stable", source_id="tb-1", store=store
            )
            is True,
        )

        before = dict(evidence["msnap_1"])
        try:
            asyncio.run(
                discover_toolbox(
                    "tools",
                    "2",
                    toolbox_resolver=lambda _name, _version: {
                        "kind": "toolbox",
                        "id": "tb-1",
                        "name": "tools",
                        "version": "2",
                        "url": "https://must-not-persist.invalid/mcp",
                    },
                    mcp_factory=lambda **_kwargs: (_ for _ in ()).throw(
                        TimeoutError("remote timeout with metadata")
                    ),
                    source_store=store,
                )
            )
        except TimeoutError:
            check("timeout original é preservado", True)
        else:
            check("timeout original é preservado", False)
        stale = get_mcp_source("tb-1", store=store)
        assert stale is not None
        check("falha operacional projeta stale", stale["status"] == "stale")
        check("último snapshot é preservado", stale["latestSnapshotId"] == "msnap_2")
        check("último review é preservado", stale["reviewedSnapshotId"] == "msnap_1")
        check("snapshot imutável não é alterado", evidence["msnap_1"] == before)
        check("URL remota não entra na projeção", "url" not in stale["source"])
        check("erro remoto não entra na projeção", "metadata" not in str(stale))
        check(
            "stale bloqueia execução antes de rede",
            source_tool_is_current(
                "msnap_1", "query", source_id="tb-1", store=store
            )
            is False,
        )

        set_current_tenant(SimpleNamespace(tid="tenant-b"))
        check(
            "estado stale não cruza tenant",
            source_tool_is_current(
                "msnap_1", "query", source_id="tb-1", store=store
            )
            is False,
        )
    finally:
        set_current_tenant(None)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
