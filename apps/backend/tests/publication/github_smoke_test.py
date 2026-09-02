"""Smoke infra-gated da publicação GitHub via Foundry Toolbox e OAuth gerenciado.

Requer PUBLICATION_TOOLBOX_ENDPOINT, PUBLICATION_SMOKE_OWNER,
PUBLICATION_SMOKE_REPOSITORY e PUBLICATION_SMOKE_RUN_ID. Cada tool é apresentada no
terminal e exige a decisão humana literal `approve`; nenhuma credencial é recebida.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys


def _config() -> dict[str, str] | None:
    names = (
        "PUBLICATION_TOOLBOX_ENDPOINT",
        "PUBLICATION_SMOKE_OWNER",
        "PUBLICATION_SMOKE_REPOSITORY",
        "PUBLICATION_SMOKE_RUN_ID",
    )
    values = {name: os.environ.get(name, "").strip() for name in names}
    if not all(values.values()) or not sys.stdin.isatty():
        return None
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", values["PUBLICATION_SMOKE_RUN_ID"]):
        raise ValueError("PUBLICATION_SMOKE_RUN_ID_INVALID")
    return values


async def _run(config: dict[str, str]) -> None:
    from app.modules.publication.internal.github import _safe_pull_request
    from app.modules.publication.public import (
        FoundryToolboxGateway,
        PublicationConsentRequired,
        PublicationExternalError,
    )

    gateway = FoundryToolboxGateway(config["PUBLICATION_TOOLBOX_ENDPOINT"])
    owner = config["PUBLICATION_SMOKE_OWNER"]
    repository = config["PUBLICATION_SMOKE_REPOSITORY"]
    run_id = config["PUBLICATION_SMOKE_RUN_ID"]
    base = os.environ.get("PUBLICATION_SMOKE_BASE_BRANCH", "main").strip() or "main"
    branch = f"assured/smoke-{run_id}"
    common = {"owner": owner, "repo": repository}

    async def invoke(tool: str, arguments: dict) -> object:
        approval = await gateway.request_approval(tool, arguments)
        print(f"\nTool: {approval.tool}\nArguments: {approval.arguments}")
        answer = await asyncio.to_thread(
            input, "Type 'approve' to execute this call: "
        )
        approved = answer.strip() == "approve"
        return await gateway.decide(approval.id, approved=approved)

    query = f"repo:{owner}/{repository} is:pr head:{branch}"
    try:
        found = await invoke("search_pull_requests", {"query": query})
        try:
            number, url = _safe_pull_request(found, owner, repository)
            print(f"Existing pull request found: {url}")
        except PublicationExternalError:
            await invoke(
                "create_branch",
                {**common, "branch": branch, "from_branch": base},
            )
            await invoke(
                "push_files",
                {
                    **common,
                    "branch": branch,
                    "files": [
                        {
                            "path": f"okf/smoke/{run_id}.yaml",
                            "content": f"kind: smoke\nmetadata:\n  id: {run_id}\n",
                        }
                    ],
                    "message": f"Publication smoke {run_id}",
                },
            )
            created = await invoke(
                "create_pull_request",
                {
                    **common,
                    "title": f"Publication smoke {run_id}",
                    "body": "Infra-gated verification of managed GitHub publication.",
                    "head": branch,
                    "base": base,
                },
            )
            number, url = _safe_pull_request(created, owner, repository)

        verified = await invoke(
            "pull_request_read",
            {**common, "pullNumber": number, "method": "get"},
        )
        assert branch in repr(verified) and base in repr(verified), "PR_VERIFICATION_FAILED"
        replay = await invoke("search_pull_requests", {"query": query})
        replay_number, replay_url = _safe_pull_request(replay, owner, repository)
        assert (replay_number, replay_url) == (number, url), "PR_REPLAY_MISMATCH"
        print(f"GitHub publication smoke: PASS ({url})")
    except PublicationConsentRequired as exc:
        print(f"Consent required for {exc.server_label}: {exc.consent_url}")
        raise


def main() -> int:
    config = _config()
    if config is None:
        print(
            "GitHub publication smoke skipped: set PUBLICATION_TOOLBOX_ENDPOINT, "
            "PUBLICATION_SMOKE_OWNER, PUBLICATION_SMOKE_REPOSITORY and "
            "PUBLICATION_SMOKE_RUN_ID, then run from an interactive terminal."
        )
        return 0
    asyncio.run(_run(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
