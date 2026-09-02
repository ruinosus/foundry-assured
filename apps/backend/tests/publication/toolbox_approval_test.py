"""O adapter usa o executor de aprovação do Agent Framework, não tools/call direto."""

from __future__ import annotations

import asyncio
import json
from typing import ClassVar

from agent_framework import FunctionTool


class Credential:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class Toolbox:
    def __init__(self, function: FunctionTool) -> None:
        self.functions = [function]
        self.entered = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *_exc) -> None:
        self.entered = False

    async def call_tool(self, *_args, **_kwargs):
        raise AssertionError("call_tool bypasses framework approval")


def main() -> int:
    from mcp import McpError
    from mcp.types import ErrorData

    from app.modules.publication.public import (
        FoundryToolboxGateway,
        PublicationConsentRequired,
        PublicationExternalError,
    )

    executions: list[dict] = []

    async def protected_create_branch(owner: str, repo: str, branch: str) -> dict:
        executions.append({"owner": owner, "repo": repo, "branch": branch})
        return {"ok": True, "branch": branch}

    function = FunctionTool(
        name="foundrygithubmcp.create_branch",
        description="Create a branch through GitHub MCP.",
        func=protected_create_branch,
    )
    toolbox = Toolbox(function)
    credential = Credential()
    gateway = FoundryToolboxGateway(
        "https://example.services.ai.azure.com/toolboxes/github/mcp",
        credential_factory=lambda: credential,
        toolbox_factory=lambda *_args, **_kwargs: toolbox,
    )

    approval = asyncio.run(
        gateway.request_approval(
            "create_branch",
            {"owner": "acme", "repo": "docs", "branch": "assured/change"},
        )
    )
    assert function.approval_mode == "always_require"
    assert approval.tool == "foundrygithubmcp.create_branch"
    assert approval.arguments["branch"] == "assured/change"
    assert executions == []
    assert credential.closed is False
    result = asyncio.run(gateway.decide(approval.id, approved=True))
    assert executions == [{"owner": "acme", "repo": "docs", "branch": "assured/change"}]
    assert json.loads(result) == {"ok": True, "branch": "assured/change"}
    assert credential.closed is True
    assert toolbox.entered is False

    rejected_executions: list[dict] = []

    async def rejected_branch(owner: str, repo: str, branch: str) -> dict:
        rejected_executions.append({"owner": owner, "repo": repo, "branch": branch})
        return {"ok": True}

    rejected_gateway = FoundryToolboxGateway(
        "https://example.services.ai.azure.com/toolboxes/github/mcp",
        credential_factory=Credential,
        toolbox_factory=lambda *_args, **_kwargs: Toolbox(
            FunctionTool(
                name="foundrygithubmcp.create_branch",
                description="Rejected tool.",
                func=rejected_branch,
            )
        ),
    )
    rejected_approval = asyncio.run(
        rejected_gateway.request_approval(
            "create_branch", {"owner": "acme", "repo": "docs", "branch": "x"}
        )
    )
    rejection = ""
    try:
        asyncio.run(rejected_gateway.decide(rejected_approval.id, approved=False))
    except PublicationExternalError as exc:
        rejection = str(exc)
    assert rejection == "PUBLICATION_APPROVAL_REJECTED"
    assert rejected_executions == []

    wrong_function = FunctionTool(
        name="anothermcp.create_branch",
        description="Wrong server.",
        func=protected_create_branch,
    )
    wrong_gateway = FoundryToolboxGateway(
        "https://example.services.ai.azure.com/toolboxes/github/mcp",
        credential_factory=Credential,
        toolbox_factory=lambda *_args, **_kwargs: Toolbox(wrong_function),
    )
    wrong_error = ""
    try:
        asyncio.run(
            wrong_gateway.request_approval(
                "create_branch", {"owner": "acme", "repo": "docs", "branch": "x"}
            )
        )
    except PublicationExternalError as exc:
        wrong_error = str(exc)
    assert wrong_error == "PUBLICATION_TOOL_NOT_AVAILABLE"

    failing_attempts = 0

    async def failing_branch(owner: str, repo: str, branch: str) -> dict:
        nonlocal failing_attempts
        failing_attempts += 1
        raise RuntimeError(f"transport failed for {owner}/{repo}:{branch}")

    failing_gateway = FoundryToolboxGateway(
        "https://example.services.ai.azure.com/toolboxes/github/mcp",
        credential_factory=Credential,
        toolbox_factory=lambda *_args, **_kwargs: Toolbox(
            FunctionTool(
                name="foundrygithubmcp.create_branch",
                description="Failing tool.",
                func=failing_branch,
            )
        ),
    )
    failing_approval = asyncio.run(
        failing_gateway.request_approval(
            "create_branch", {"owner": "acme", "repo": "docs", "branch": "x"}
        )
    )
    failure_message = ""
    try:
        asyncio.run(failing_gateway.decide(failing_approval.id, approved=True))
    except RuntimeError as exc:
        failure_message = str(exc)
    assert "transport failed" in failure_message
    assert failing_attempts == 1

    transient_attempts = 0

    class TransientError(RuntimeError):
        status_code = 429
        headers: ClassVar = {"Retry-After": "0"}

    async def transient_search(query: str) -> dict:
        nonlocal transient_attempts
        transient_attempts += 1
        if transient_attempts < 3:
            raise TransientError("rate limited")
        return {"ok": True, "query": query}

    transient_gateway = FoundryToolboxGateway(
        "https://example.services.ai.azure.com/toolboxes/github/mcp",
        credential_factory=Credential,
        toolbox_factory=lambda *_args, **_kwargs: Toolbox(
            FunctionTool(
                name="foundrygithubmcp.search_pull_requests",
                description="Transient tool.",
                func=transient_search,
            )
        ),
    )
    transient_approval = asyncio.run(
        transient_gateway.request_approval(
            "search_pull_requests", {"query": "repo:acme/docs is:pr"}
        )
    )
    transient_result = asyncio.run(
        transient_gateway.decide(transient_approval.id, approved=True)
    )
    assert transient_attempts == 3
    assert json.loads(transient_result)["ok"] is True

    async def consent_branch(owner: str, repo: str, branch: str) -> dict:
        message = (
            'gateway {"errors":[{"name":"foundrygithubmcp","type":"mcp",'
            '"error":{"code":"CONSENT_REQUIRED",'
            '"message":"https://consent.example"}}]}'
        )
        raise McpError(ErrorData(code=-32006, message=message))

    consent_gateway = FoundryToolboxGateway(
        "https://example.services.ai.azure.com/toolboxes/github/mcp",
        credential_factory=Credential,
        toolbox_factory=lambda *_args, **_kwargs: Toolbox(
            FunctionTool(
                name="foundrygithubmcp.create_branch",
                description="Consent tool.",
                func=consent_branch,
            )
        ),
    )
    consent_approval = asyncio.run(
        consent_gateway.request_approval(
            "create_branch", {"owner": "acme", "repo": "docs", "branch": "x"}
        )
    )
    consent_url = ""
    try:
        asyncio.run(consent_gateway.decide(consent_approval.id, approved=True))
    except PublicationConsentRequired as exc:
        consent_url = exc.consent_url
    assert consent_url == "https://consent.example"

    print("toolbox native approval contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
