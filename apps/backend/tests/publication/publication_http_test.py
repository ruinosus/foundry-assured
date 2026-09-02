"""Contrato HTTP da publicação aprovada."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


class PublicationService:
    def __init__(self, projection) -> None:
        self.projection = projection
        self.calls = 0

    async def publish(self, scope, request, *, roles):
        from app.modules.publication.public import (
            PublicationOutcome,
            ToolApprovalRequest,
        )

        assert roles == {"Approver"}
        assert scope.area_id == "area-a"
        self.calls += 1
        return PublicationOutcome(
            self.projection,
            ToolApprovalRequest(
                "a" * 32,
                "foundrygithubmcp.create_branch",
                {"branch": self.projection.branch},
            ),
            False,
        )

    async def decide(self, scope, publication_id, approval_id, *, approved, roles):
        from app.modules.publication.public import PublicationOutcome

        assert publication_id == self.projection.id
        assert approval_id == "a" * 32
        assert approved is True
        assert roles == {"Approver"}
        return PublicationOutcome(self.projection, None, False)

    def get(self, scope, publication_id: str):
        assert publication_id == self.projection.id
        return self.projection


def main() -> int:
    from app.modules.authoring.public import ChangeSetScope
    from app.modules.publication import api
    from app.modules.publication.public import StoredPublication
    from app.shared import auth

    projection = StoredPublication(
        id="123e4567-e89b-42d3-a456-426614174001",
        changeset_id="123e4567-e89b-42d3-a456-426614174000",
        revision=3,
        content_hash="a" * 64,
        owner="acme",
        repository="docs",
        base_branch="main",
        target_directory="okf",
        branch="assured/123e4567-aaaaaaaaaaaa",
        pull_request_number=42,
        pull_request_url="https://github.com/acme/docs/pull/42",
        state="completed",
        step="completed",
        approval_id="",
        error_code="",
        created_at="2026-09-01T12:00:00+00:00",
        updated_at="2026-09-01T12:00:01+00:00",
    )
    service = PublicationService(projection)
    application = FastAPI()
    application.include_router(api.router)
    application.dependency_overrides[api.require_area] = lambda: None
    application.dependency_overrides[api._scope] = lambda: ChangeSetScope(
        "tenant-a", "area-a", "approver-a"
    )
    application.dependency_overrides[api.default_publication_service] = lambda: service
    user = SimpleNamespace(oid="approver-a", roles=["Approver"])
    application.dependency_overrides[auth.require_user] = lambda: user
    if auth.azure_scheme is not None:
        application.dependency_overrides[auth.azure_scheme] = lambda: user
    api.current_roles = lambda: {"Approver"}
    client = TestClient(application)
    body = {
        "changeset_id": projection.changeset_id,
        "revision": projection.revision,
        "content_hash": projection.content_hash,
        "owner": projection.owner,
        "repository": projection.repository,
        "base_branch": projection.base_branch,
        "target_directory": "okf",
    }

    created = client.post(
        "/authoring/publications",
        headers={"Idempotency-Key": "publish-http-001"},
        json=body,
    )
    assert created.status_code == 202, created.text
    assert created.headers["Idempotent-Replay"] == "false"
    assert created.headers["Cache-Control"] == "no-store"
    assert created.json()["approval"]["tool"] == "foundrygithubmcp.create_branch"
    assert (
        created.json()["publication"]["pull_request_url"] == projection.pull_request_url
    )
    assert "raw_response" not in created.text.lower()
    assert "token" not in created.text.lower()

    approved = client.post(
        f"/authoring/publications/{projection.id}/approvals",
        json={"approval_id": "a" * 32, "approved": True},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["publication"]["state"] == "completed"

    before = service.calls
    read = client.get(f"/authoring/publications/{projection.id}")
    assert read.status_code == 200, read.text
    assert read.json()["state"] == "completed"
    assert service.calls == before

    invalid = client.post(
        "/authoring/publications",
        headers={"Idempotency-Key": "publish-http-002"},
        json={**body, "unexpected": True},
    )
    assert invalid.status_code == 422, invalid.text

    application.dependency_overrides.clear()
    api.current_roles = lambda: set()
    print("publication http contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
