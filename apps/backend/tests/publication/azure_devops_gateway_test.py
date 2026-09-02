"""Contrato REST 7.1 e OBO do adapter Azure DevOps."""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from azure.core.exceptions import ClientAuthenticationError


class Credential:
    def __init__(self) -> None:
        self.scopes: list[tuple[str, ...]] = []

    def get_token(self, *scopes: str):
        self.scopes.append(scopes)
        return type("AccessToken", (), {"token": "delegated-token"})()


class AuthResponse:
    status_code = 400
    reason = "Bad Request"

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    @staticmethod
    def text() -> str:
        return json.dumps(
            {
                "error": "interaction_required",
                "claims": '{"access_token":{"polids":{"essential":true}}}',
            }
        )

    def json(self) -> dict:
        return json.loads(self.text())


class ChallengedCredential:
    def get_token(self, *scopes: str):
        raise ClientAuthenticationError(response=AuthResponse())


def _push_arguments() -> dict:
    return {
        "organization": "acme",
        "project": "platform",
        "repository": "docs",
        "source_ref": "refs/heads/assured/change",
        "old_object_id": "a" * 40,
        "message": "Publish approved ChangeSet",
        "changes": [
            {
                "change_type": "add",
                "path": "okf/policy/safe-output.yaml",
                "content": "kind: policy\n",
            }
        ],
    }


def main() -> int:
    from app.modules.publication.internal.azure_devops import (
        AZURE_DEVOPS_PERMISSION,
        AZURE_DEVOPS_TOKEN_SCOPE,
        AzureDevOpsAuthenticationRequired,
        AzureDevOpsRestGateway,
    )
    from app.modules.publication.public import (
        PublicationConflict,
        PublicationExternalError,
    )

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "dev.azure.com"
        assert request.url.params["api-version"] == "7.1"
        assert request.headers["Authorization"] == "Bearer delegated-token"
        if request.url.path.endswith("/pushes"):
            body = json.loads(request.content)
            assert body["refUpdates"] == [
                {
                    "name": "refs/heads/assured/change",
                    "oldObjectId": "a" * 40,
                }
            ]
            assert body["commits"][0]["changes"][0] == {
                "changeType": "add",
                "item": {"path": "/okf/policy/safe-output.yaml"},
                "newContent": {"content": "kind: policy\n", "contentType": "rawtext"},
            }
            return httpx.Response(
                201,
                json={
                    "commits": [{"commitId": "b" * 40}],
                    "refUpdates": [
                        {
                            "name": "refs/heads/assured/change",
                            "oldObjectId": "a" * 40,
                            "newObjectId": "b" * 40,
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    credential = Credential()
    gateway = AzureDevOpsRestGateway(
        credential_factory=lambda: credential,
        transport=httpx.MockTransport(handler),
    )
    approval = asyncio.run(
        gateway.request_approval(
            "push",
            _push_arguments(),
        )
    )
    assert requests == []
    result = asyncio.run(gateway.decide(approval.id, approved=True))
    assert result["commit_id"] == "b" * 40
    assert credential.scopes == [(AZURE_DEVOPS_TOKEN_SCOPE,)]
    assert AZURE_DEVOPS_TOKEN_SCOPE == "499b84ac-1321-427f-aa17-267ca6975798/.default"
    assert AZURE_DEVOPS_PERMISSION == "vso.code_write"

    attempts = 0

    def stale_ref(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            409,
            json={"updateStatus": "staleOldObjectId", "message": "ref changed"},
        )

    conflict_gateway = AzureDevOpsRestGateway(
        credential_factory=Credential,
        transport=httpx.MockTransport(stale_ref),
    )
    conflict_approval = asyncio.run(
        conflict_gateway.request_approval(
            "push",
            _push_arguments(),
        )
    )
    conflict = ""
    try:
        asyncio.run(conflict_gateway.decide(conflict_approval.id, approved=True))
    except PublicationConflict as exc:
        conflict = str(exc)
    assert conflict == "PUBLICATION_REF_CONFLICT"
    assert attempts == 1

    challenged = AzureDevOpsRestGateway(credential_factory=ChallengedCredential)
    challenged_approval = asyncio.run(
        challenged.request_approval(
            "get_ref",
            {
                "organization": "acme",
                "project": "platform",
                "repository": "docs",
                "source_ref": "refs/heads/main",
            },
        )
    )
    challenge = ""
    try:
        asyncio.run(challenged.decide(challenged_approval.id, approved=True))
    except AzureDevOpsAuthenticationRequired as exc:
        challenge = exc.claims
    assert challenge == '{"access_token":{"polids":{"essential":true}}}'

    transient_attempts = 0

    def transient_read(request: httpx.Request) -> httpx.Response:
        nonlocal transient_attempts
        statuses = (408, 429, 500)
        status = statuses[transient_attempts]
        transient_attempts += 1
        headers = {"Retry-After": "3"} if status == 429 else None
        return httpx.Response(status, headers=headers)

    transient_gateway = AzureDevOpsRestGateway(
        credential_factory=Credential,
        transport=httpx.MockTransport(transient_read),
    )
    transient_approval = asyncio.run(
        transient_gateway.request_approval(
            "get_ref",
            {
                "organization": "acme",
                "project": "platform",
                "repository": "docs",
                "source_ref": "refs/heads/main",
            },
        )
    )
    transient_error = ""
    sleep = AsyncMock()
    with patch(
        "app.modules.publication.internal.azure_devops.random.uniform",
        return_value=0.25,
    ), patch(
        "app.modules.publication.internal.azure_devops.asyncio.sleep", sleep
    ):
        try:
            asyncio.run(transient_gateway.decide(transient_approval.id, approved=True))
        except PublicationExternalError as exc:
            transient_error = str(exc)
    assert transient_error == "PUBLICATION_AZURE_DEVOPS_TRANSIENT"
    assert transient_attempts == 3
    assert [call.args[0] for call in sleep.await_args_list] == [1.25, 3.25]

    fixed_now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    retry_at = format_datetime(datetime(2026, 9, 2, 12, 0, 7, tzinfo=UTC), usegmt=True)
    dated_response = httpx.Response(429, headers={"Retry-After": retry_at})
    with patch(
        "app.modules.publication.internal.azure_devops.random.uniform",
        return_value=0.25,
    ):
        assert AzureDevOpsRestGateway._retry_delay(
            dated_response, 0, now=fixed_now
        ) == 7.25

    async def assert_write_not_retried(response_or_error) -> None:
        write_attempts = 0

        def write_failure(request: httpx.Request) -> httpx.Response:
            nonlocal write_attempts
            write_attempts += 1
            if isinstance(response_or_error, Exception):
                raise response_or_error
            return httpx.Response(response_or_error)

        failed_gateway = AzureDevOpsRestGateway(
            credential_factory=Credential,
            transport=httpx.MockTransport(write_failure),
        )
        failed_approval = await failed_gateway.request_approval(
            "push", _push_arguments()
        )
        try:
            await failed_gateway.decide(failed_approval.id, approved=True)
        except PublicationExternalError:
            pass
        assert write_attempts == 1

    asyncio.run(assert_write_not_retried(httpx.ConnectError("offline")))
    asyncio.run(assert_write_not_retried(500))
    asyncio.run(assert_write_not_retried(400))

    read_4xx_attempts = 0

    def read_4xx(request: httpx.Request) -> httpx.Response:
        nonlocal read_4xx_attempts
        read_4xx_attempts += 1
        return httpx.Response(400)

    read_4xx_gateway = AzureDevOpsRestGateway(
        credential_factory=Credential,
        transport=httpx.MockTransport(read_4xx),
    )
    read_4xx_approval = asyncio.run(
        read_4xx_gateway.request_approval(
            "get_ref",
            {
                "organization": "acme",
                "project": "platform",
                "repository": "docs",
                "source_ref": "refs/heads/main",
            },
        )
    )
    try:
        asyncio.run(read_4xx_gateway.decide(read_4xx_approval.id, approved=True))
    except PublicationExternalError:
        pass
    assert read_4xx_attempts == 1

    transport_calls = 0

    def rejected_transport(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("human rejection must not perform egress")

    rejected_gateway = AzureDevOpsRestGateway(
        credential_factory=Credential,
        transport=httpx.MockTransport(rejected_transport),
    )
    rejected_approval = asyncio.run(
        rejected_gateway.request_approval("push", _push_arguments())
    )
    rejected = ""
    try:
        asyncio.run(rejected_gateway.decide(rejected_approval.id, approved=False))
    except PublicationExternalError as exc:
        rejected = str(exc)
    assert rejected == "PUBLICATION_APPROVAL_REJECTED"
    assert transport_calls == 0

    transport_attempts = 0

    def transport_read(request: httpx.Request) -> httpx.Response:
        nonlocal transport_attempts
        transport_attempts += 1
        raise httpx.ConnectError("offline", request=request)

    transport_gateway = AzureDevOpsRestGateway(
        credential_factory=Credential,
        transport=httpx.MockTransport(transport_read),
    )
    transport_approval = asyncio.run(
        transport_gateway.request_approval(
            "get_ref",
            {
                "organization": "acme",
                "project": "platform",
                "repository": "docs",
                "source_ref": "refs/heads/main",
            },
        )
    )
    with patch(
        "app.modules.publication.internal.azure_devops.asyncio.sleep",
        AsyncMock(),
    ):
        try:
            asyncio.run(transport_gateway.decide(transport_approval.id, approved=True))
        except PublicationExternalError:
            pass
    assert transport_attempts == 3

    import app

    backend_root = Path(app.__file__).resolve().parent.parent
    repository_root = backend_root.parent.parent
    validator = repository_root / "scripts" / "validate-azure-devops-permissions.sh"
    allowed = subprocess.run(
        ["bash", str(validator), "scope-write", "scope-write"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 0, allowed.stderr
    excessive = subprocess.run(
        ["bash", str(validator), "scope-write", "scope-write\nscope-read"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert excessive.returncode != 0
    assert "AZURE_DEVOPS_PERMISSION_EXCESSIVE" in excessive.stderr
    setup = (repository_root / "scripts" / "setup-entra.sh").read_text()
    assert 'AZURE_DEVOPS_APPID="499b84ac-1321-427f-aa17-267ca6975798"' in setup
    assert "oauth2PermissionScopes[?value=='vso.code_write']" in setup
    assert '"$AZURE_DEVOPS_SCOPE_ID=Scope"' in setup

    print("publication azure devops gateway contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
