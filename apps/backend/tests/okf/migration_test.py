"""Compatibilidade e migração explícita dos manifestos OKF existentes."""

from __future__ import annotations

import sys
from copy import deepcopy

from app.modules.formflow.public import (
    list_copilots,
    list_flows,
    load_copilot,
    load_flow,
)
from app.modules.okf.public import (
    LEGACY_MANIFEST_FORMAT,
    AuthoringInvalid,
    migrate_legacy_manifest,
)

_MIGRATION = {
    "source_format": LEGACY_MANIFEST_FORMAT,
    "tenant": "tenant-a",
    "area": "authoring",
    "revision": "1",
    "generated_by": "human:migration-test",
    "generated_at": "2026-08-31T12:00:00Z",
}


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    flows = {name: load_flow(name) for name in list_flows()}
    copilots = {name: load_copilot(name) for name in list_copilots()}
    original_legacy = deepcopy((flows, copilots))
    check("legacy formflows remain readable", set(flows) == {"agent", "copilot", "knowledge", "skill"})
    check("legacy copilots and policies remain readable", set(copilots) == {"builder", "hitl"})

    migrated_flows = [
        migrate_legacy_manifest(flow, doc_type="formflow", identifier=name, **_MIGRATION)
        for name, flow in flows.items()
    ]
    check("all legacy formflows migrate deterministically", len(migrated_flows) == 4)
    check("migration creates drafts", all(doc.publication_state == "draft" for doc in migrated_flows))

    builder = migrate_legacy_manifest(
        copilots["builder"],
        doc_type="copilot",
        identifier="builder",
        replacement_spec={
            "writes": [{"type": "formflow", "operations": ["revise"]}],
            "cannotWrite": [{"type": "policy"}],
        },
        **_MIGRATION,
    )
    hitl = migrate_legacy_manifest(
        copilots["hitl"],
        doc_type="policy",
        identifier="hitl",
        replacement_spec={
            "enforcement": "external",
            "sources": ["foundry-tool-approval", "entra-app-roles"],
        },
        **_MIGRATION,
    )
    check("copilot migration uses explicit authoring grants", builder.spec["writes"][0]["type"] == "formflow")
    check("policy migration remains non-executable", hitl.spec["enforcement"] == "external")
    check("migration does not mutate legacy inputs", (flows, copilots) == original_legacy)

    def refuses(name: str, **kwargs: object) -> None:
        try:
            migrate_legacy_manifest(copilots["builder"], **kwargs)
        except AuthoringInvalid:
            check(name, True)
        else:
            check(name, False)

    refuses(
        "copilot is never converted semantically by inference",
        doc_type="copilot",
        identifier="builder",
        **_MIGRATION,
    )
    refuses(
        "docbundles remain upstream-only by default",
        doc_type="docbundle",
        identifier="wiki",
        replacement_spec={},
        **_MIGRATION,
    )
    refuses(
        "unknown source format is rejected",
        source_format="legacy-unknown",
        doc_type="copilot",
        identifier="builder",
        replacement_spec={},
        **{key: value for key, value in _MIGRATION.items() if key != "source_format"},
    )

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
