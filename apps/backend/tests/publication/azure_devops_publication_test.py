"""Contrato F12: publicação Azure DevOps delegada e idempotente."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import MappingProxyType, SimpleNamespace


class Gateway:
    def __init__(self, *, conflict: bool = False, challenge_once: bool = False) -> None:
        self.pending: dict[str, tuple[str, dict]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.counter = 0
        self.conflict = conflict
        self.challenge_once = challenge_once

    async def request_approval(self, tool: str, arguments: dict):
        from app.modules.publication.public import ToolApprovalRequest

        self.counter += 1
        approval_id = f"{self.counter:032x}"
        self.pending[approval_id] = (tool, arguments)
        return ToolApprovalRequest(approval_id, f"azuredevops.{tool}", arguments)

    async def decide(self, approval_id: str, *, approved: bool):
        from app.modules.publication.public import (
            AzureDevOpsAuthenticationRequired,
            PublicationConflict,
        )

        assert approved
        if self.challenge_once:
            self.challenge_once = False
            raise AzureDevOpsAuthenticationRequired(
                '{"access_token":{"polids":{"essential":true}}}'
            )
        tool, arguments = self.pending.pop(approval_id)
        self.calls.append((tool, arguments))
        if tool == "find_pull_request":
            return {"found": False}
        if tool == "get_ref":
            return {"source_ref": "refs/heads/main", "object_id": "a" * 40}
        if tool == "push":
            if self.conflict:
                raise PublicationConflict("PUBLICATION_REF_CONFLICT")
            return {
                "source_ref": arguments["source_ref"],
                "commit_id": "b" * 40,
            }
        if tool == "create_pull_request":
            return {
                "found": True,
                "pull_request_id": 42,
                "pull_request_url": (
                    "https://dev.azure.com/acme/platform/_git/docs/pullrequest/42"
                ),
                "source_ref": arguments["source_ref"],
                "target_ref": arguments["target_ref"],
                "status": "active",
                "merge_status": "queued",
            }
        if tool == "read_pull_request":
            return {
                "found": True,
                "pull_request_id": 42,
                "pull_request_url": (
                    "https://dev.azure.com/acme/platform/_git/docs/pullrequest/42"
                ),
                "source_ref": arguments["source_ref"],
                "target_ref": arguments["target_ref"],
                "status": "active",
                "merge_status": "succeeded",
            }
        raise AssertionError(tool)


class ChangeSets:
    def __init__(self, changeset) -> None:
        self.changeset = changeset

    def get(self, scope, changeset_id: str):
        assert scope.area_id == "area-a"
        assert changeset_id == self.changeset.id
        return self.changeset


class Decisions:
    def __init__(self, changeset) -> None:
        self.changeset = changeset

    def assert_approved(self, scope, changeset_id: str):
        assert scope.actor_id == "approver-a"
        assert changeset_id == self.changeset.id
        return SimpleNamespace(
            revision=self.changeset.revision,
            content_hash=self.changeset.content_hash,
        )


def _finish(service, scope, outcome):
    while outcome.approval is not None:
        outcome = asyncio.run(
            service.decide(
                scope,
                outcome.publication.id,
                outcome.approval.id,
                approved=True,
                roles={"Approver"},
            )
        )
    return outcome


def _complete(service, scope, request):
    outcome = asyncio.run(service.publish(scope, request, roles={"Approver"}))
    return _finish(service, scope, outcome)


def main() -> int:
    from app.modules.authoring.public import ChangeSetScope
    from app.modules.publication.internal.azure_devops import (
        AzureDevOpsPublicationRequest,
        AzureDevOpsPublicationService,
    )
    from app.modules.publication.public import (
        AzureDevOpsAuthenticationRequired,
        PublicationConflict,
        SQLitePublicationRepository,
    )

    changeset = SimpleNamespace(
        id="123e4567-e89b-42d3-a456-426614174000",
        revision=3,
        content_hash="a" * 64,
        content=MappingProxyType(
            {
                "operations": (
                    MappingProxyType(
                        {
                            "id": "safe-output",
                            "operation": "create",
                            "document_type": "policy",
                            "document": "kind: policy\r\n",
                        }
                    ),
                )
            }
        ),
        state="approved",
    )
    scope = ChangeSetScope("tenant-a", "area-a", "approver-a")
    request = AzureDevOpsPublicationRequest(
        changeset_id=changeset.id,
        revision=3,
        content_hash="a" * 64,
        organization="acme",
        project="platform",
        repository="docs",
        base_branch="main",
        target_directory="okf",
        idempotency_key="azure-devops-publication-001",
    )
    with tempfile.TemporaryDirectory() as directory:
        repository = SQLitePublicationRepository(Path(directory) / "publication.sqlite3")
        gateway = Gateway()
        service = AzureDevOpsPublicationService(
            changesets=ChangeSets(changeset),
            decisions=Decisions(changeset),
            repository=repository,
            gateway=gateway,
        )
        outcome = _complete(service, scope, request)
        publication = outcome.publication
        assert publication.state == "completed"
        assert publication.provider == "azure_devops"
        assert publication.project == "platform"
        assert publication.base_object_id == "a" * 40
        assert publication.commit_id == "b" * 40
        assert publication.merge_status == "succeeded"
        assert [tool for tool, _ in gateway.calls] == [
            "find_pull_request",
            "get_ref",
            "push",
            "create_pull_request",
            "read_pull_request",
        ]
        pushed = gateway.calls[2][1]
        assert pushed["changes"] == [
            {
                "change_type": "add",
                "path": "okf/policy/safe-output.yaml",
                "content": "kind: policy\n",
            }
        ]
        replay = asyncio.run(service.publish(scope, request, roles={"Approver"}))
        assert replay.replay is True
        assert replay.publication.id == publication.id
        assert len(gateway.calls) == 5
        persisted = repr(repository.get(scope, publication.id)).lower()
        assert all(
            marker not in persisted
            for marker in ("delegated-token", "authorization", "bearer ", "raw_response")
        )

        conflict_gateway = Gateway(conflict=True)
        conflict_service = AzureDevOpsPublicationService(
            changesets=ChangeSets(changeset),
            decisions=Decisions(changeset),
            repository=repository,
            gateway=conflict_gateway,
        )
        conflict_request = AzureDevOpsPublicationRequest(
            **{
                **request.to_dict(),
                "idempotency_key": "azure-devops-conflict-001",
            }
        )
        conflict_outcome = asyncio.run(
            conflict_service.publish(scope, conflict_request, roles={"Approver"})
        )
        for _ in range(2):
            conflict_outcome = asyncio.run(
                conflict_service.decide(
                    scope,
                    conflict_outcome.publication.id,
                    conflict_outcome.approval.id,
                    approved=True,
                    roles={"Approver"},
                )
            )
        conflict_code = ""
        try:
            asyncio.run(
                conflict_service.decide(
                    scope,
                    conflict_outcome.publication.id,
                    conflict_outcome.approval.id,
                    approved=True,
                    roles={"Approver"},
                )
            )
        except PublicationConflict as exc:
            conflict_code = str(exc)
        assert conflict_code == "PUBLICATION_REF_CONFLICT"
        interrupted = repository.get(scope, conflict_outcome.publication.id)
        assert interrupted is not None
        assert interrupted.state == "intervention_required"
        assert [tool for tool, _ in conflict_gateway.calls].count("push") == 1

        challenged_gateway = Gateway(challenge_once=True)
        challenged_service = AzureDevOpsPublicationService(
            changesets=ChangeSets(changeset),
            decisions=Decisions(changeset),
            repository=repository,
            gateway=challenged_gateway,
        )
        challenged_request = AzureDevOpsPublicationRequest(
            **{
                **request.to_dict(),
                "idempotency_key": "azure-devops-step-up-001",
            }
        )
        challenged_outcome = asyncio.run(
            challenged_service.publish(scope, challenged_request, roles={"Approver"})
        )
        approval_id = challenged_outcome.approval.id
        challenge = ""
        try:
            asyncio.run(
                challenged_service.decide(
                    scope,
                    challenged_outcome.publication.id,
                    approval_id,
                    approved=True,
                    roles={"Approver"},
                )
            )
        except AzureDevOpsAuthenticationRequired as exc:
            challenge = exc.claims
        assert challenge
        restored = repository.get(scope, challenged_outcome.publication.id)
        assert restored is not None
        assert restored.state == "awaiting_approval"
        assert restored.approval_id == approval_id
        resumed = asyncio.run(
            challenged_service.decide(
                scope,
                challenged_outcome.publication.id,
                approval_id,
                approved=True,
                roles={"Approver"},
            )
        )
        completed_after_step_up = _finish(challenged_service, scope, resumed)
        assert completed_after_step_up.publication.state == "completed"
        assert [tool for tool, _ in challenged_gateway.calls].count(
            "find_pull_request"
        ) == 1

    print("publication azure devops contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
