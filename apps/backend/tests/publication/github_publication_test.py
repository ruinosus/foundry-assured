"""Contrato F11: publicação GitHub delegada, exata e idempotente."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import MappingProxyType, SimpleNamespace


def check(label: str, condition=True, *, fails: bool = False) -> None:
    try:
        result = condition() if callable(condition) else condition
        ok = bool(result)
    except Exception:  # noqa: BLE001 - o helper comprova contratos negativos.
        ok = fails
    else:
        ok = not ok if fails else ok
    if not ok:
        raise AssertionError(label)
    print(f"  ok  {label}")


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.pending: dict[str, tuple[str, dict]] = {}
        self.counter = 0

    async def request_approval(self, tool: str, arguments: dict):
        from app.modules.publication.public import ToolApprovalRequest

        self.counter += 1
        approval_id = f"{self.counter:032x}"
        self.pending[approval_id] = (tool, arguments)
        return ToolApprovalRequest(approval_id, f"foundrygithubmcp.{tool}", arguments)

    async def decide(self, approval_id: str, *, approved: bool) -> dict:
        assert approved
        tool, arguments = self.pending.pop(approval_id)
        self.calls.append((tool, arguments))
        if tool == "create_pull_request":
            return {"number": 42, "html_url": "https://github.com/acme/docs/pull/42"}
        if tool == "pull_request_read":
            return {
                "number": 42,
                "html_url": "https://github.com/acme/docs/pull/42",
                "state": "open",
                "head": {"ref": "assured/123e4567-aaaaaaaaaaaa"},
                "base": {"ref": "main"},
            }
        return {"ok": True}


class AmbiguousWriteGateway(FakeGateway):
    async def decide(self, approval_id: str, *, approved: bool) -> dict:
        from app.modules.publication.public import PublicationExternalError

        assert approved
        tool, arguments = self.pending.pop(approval_id)
        self.calls.append((tool, arguments))
        if tool == "create_branch":
            raise PublicationExternalError("response lost after remote write")
        return {"ok": True}


class ApprovedDecisions:
    def __init__(self, changeset) -> None:
        self.changeset = changeset
        self.calls = 0

    def assert_approved(self, scope, changeset_id: str):
        self.calls += 1
        if changeset_id != self.changeset.id:
            raise ValueError("APPROVAL_REQUIRED")
        return SimpleNamespace(
            changeset_id=changeset_id,
            revision=self.changeset.revision,
            content_hash=self.changeset.content_hash,
        )


class ChangeSets:
    def __init__(self, changeset) -> None:
        self.changeset = changeset

    def get(self, scope, changeset_id: str):
        if changeset_id != self.changeset.id or scope.area_id != "area-a":
            raise ValueError("CHANGESET_NOT_FOUND")
        return self.changeset


def main() -> int:
    from app.modules.authoring.public import ChangeSetScope
    from app.modules.publication.internal.github import (
        _safe_pull_request,
        _validated_pull_request,
    )
    from app.modules.publication.public import (
        GitHubPublicationService,
        PublicationRequest,
        SQLitePublicationRepository,
    )

    content = MappingProxyType(
        {
            "operations": (
                MappingProxyType(
                    {
                        "id": "safe-output",
                        "operation": "create",
                        "document_type": "policy",
                        "document": "kind: policy\r\nmetadata:\r\n  id: safe-output\r\n",
                    }
                ),
            )
        }
    )
    changeset = SimpleNamespace(
        id="123e4567-e89b-42d3-a456-426614174000",
        revision=3,
        content_hash="a" * 64,
        content=content,
        state="approved",
    )
    scope = ChangeSetScope("tenant-a", "area-a", "approver-a")
    request = PublicationRequest(
        changeset_id=changeset.id,
        revision=3,
        content_hash="a" * 64,
        owner="acme",
        repository="docs",
        base_branch="main",
        target_directory="okf",
        idempotency_key="publish-approved-001",
    )

    with tempfile.TemporaryDirectory() as directory:
        repository = SQLitePublicationRepository(
            Path(directory) / "publication.sqlite3"
        )
        gateway = FakeGateway()
        decisions = ApprovedDecisions(changeset)
        service = GitHubPublicationService(
            changesets=ChangeSets(changeset),
            decisions=decisions,
            repository=repository,
            gateway=gateway,
        )

        outcome = asyncio.run(service.publish(scope, request, roles={"Approver"}))
        check("first publication is not a replay", outcome.replay is False)
        expected = [
            "search_pull_requests",
            "create_branch",
            "push_files",
            "create_pull_request",
            "pull_request_read",
        ]
        for index, tool in enumerate(expected):
            approval = outcome.approval
            check(f"{tool} is presented before execution", approval is not None)
            check(
                f"{tool} has not executed before approval", len(gateway.calls) == index
            )
            check(
                f"{tool} is the presented native tool",
                approval.tool.endswith(f".{tool}"),
            )
            outcome = asyncio.run(
                service.decide(
                    scope,
                    outcome.publication.id,
                    approval.id,
                    approved=True,
                    roles={"Approver"},
                )
            )
        published = outcome.publication
        check(
            "publication completes after the verification approval",
            published.state == "completed",
        )
        check("completed publication has no pending approval", outcome.approval is None)
        check(
            "official GitHub MCP tools materialize and verify the PR",
            [tool for tool, _ in gateway.calls] == expected,
        )
        pushed = gateway.calls[2][1]
        check(
            "approved documents are normalized to LF",
            "\r" not in pushed["files"][0]["content"],
        )
        check(
            "target path is deterministic",
            pushed["files"][0]["path"] == "okf/policy/safe-output.yaml",
        )
        check(
            "branch is stable from the approved hash",
            published.branch.endswith("a" * 12),
        )
        check(
            "only a safe PR projection is persisted",
            published.pull_request_url.endswith("/pull/42"),
        )

        decisions_before_replay = decisions.calls
        replayed = asyncio.run(service.publish(scope, request, roles={"Approver"}))
        check(
            "same key replays the completed publication",
            replayed.replay and replayed.publication.id == published.id,
        )
        check("replay creates neither branch nor PR", len(gateway.calls) == 5)
        check(
            "approval is checked before every replay",
            decisions.calls == decisions_before_replay + 1,
        )
        check(
            "idempotency key cannot represent another hash",
            lambda: asyncio.run(
                service.publish(
                    scope,
                    PublicationRequest(
                        **{**request.to_dict(), "content_hash": "b" * 64}
                    ),
                    roles={"Approver"},
                )
            ),
            fails=True,
        )
        for denied in ({"Reader"}, {"Author"}, {"Admin"}):
            check(
                f"{next(iter(denied))} cannot publish without exact Approver role",
                lambda denied=denied: asyncio.run(
                    service.publish(scope, request, roles=denied)
                ),
                fails=True,
            )
        check(
            "area isolation is fail-closed",
            lambda: repository.get(
                ChangeSetScope("tenant-a", "area-b", "approver-b"), published.id
            ),
            fails=True,
        )
        persisted = repository.get(scope, published.id)
        check(
            "persistence contains no token, header, consent URL or raw response",
            all(
                marker not in repr(persisted).lower()
                for marker in ("authorization", "bearer ", "consent", "raw_response")
            ),
        )
        check(
            "invalid repository and path inputs fail before egress",
            lambda: PublicationRequest(**{**request.to_dict(), "owner": "../escape"}),
            fails=True,
        )
        check("invalid input made no external call", len(gateway.calls) == 5)
        check(
            "PR number must match its GitHub URL",
            lambda: _safe_pull_request(
                {"number": 42, "html_url": "https://github.com/acme/docs/pull/43"},
                "acme",
                "docs",
            ),
            fails=True,
        )
        check(
            "final verification rejects another head branch",
            lambda: _validated_pull_request(
                {
                    "number": 42,
                    "html_url": "https://github.com/acme/docs/pull/42",
                    "head": {"ref": "other"},
                    "base": {"ref": "main"},
                },
                owner="acme",
                repository="docs",
                number=42,
                head=published.branch,
                base="main",
            ),
            fails=True,
        )

        ambiguous_gateway = AmbiguousWriteGateway()
        ambiguous_service = GitHubPublicationService(
            changesets=ChangeSets(changeset),
            decisions=decisions,
            repository=repository,
            gateway=ambiguous_gateway,
        )
        ambiguous_request = PublicationRequest(
            **{**request.to_dict(), "idempotency_key": "ambiguous-write-001"}
        )
        ambiguous = asyncio.run(
            ambiguous_service.publish(scope, ambiguous_request, roles={"Approver"})
        )
        ambiguous = asyncio.run(
            ambiguous_service.decide(
                scope,
                ambiguous.publication.id,
                ambiguous.approval.id,
                approved=True,
                roles={"Approver"},
            )
        )
        branch_approval = ambiguous.approval
        check(
            "ambiguous branch response interrupts the saga",
            lambda: asyncio.run(
                ambiguous_service.decide(
                    scope,
                    ambiguous.publication.id,
                    branch_approval.id,
                    approved=True,
                    roles={"Approver"},
                )
            ),
            fails=True,
        )
        interrupted = repository.get(scope, ambiguous.publication.id)
        check(
            "ambiguous write requires intervention",
            interrupted is not None and interrupted.state == "intervention_required",
        )
        check(
            "same key cannot replay an ambiguous write",
            lambda: asyncio.run(
                ambiguous_service.publish(scope, ambiguous_request, roles={"Approver"})
            ),
            fails=True,
        )
        check(
            "ambiguous branch is attempted only once",
            [tool for tool, _ in ambiguous_gateway.calls].count("create_branch") == 1,
        )

    print("publication github contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
