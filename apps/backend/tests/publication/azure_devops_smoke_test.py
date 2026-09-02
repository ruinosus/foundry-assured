"""Smoke autenticado da publicação Azure DevOps pela API e pelo fluxo OBO.

Requer as variáveis PUBLICATION_AZURE_DEVOPS_* listadas em `_config`, `az login`
para o Approver e terminal interativo. O token obtido pelo Azure CLI só é enviado
como bearer para a API; a aplicação troca essa identidade por OBO e nunca recebe PAT.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any
from uuid import UUID

import httpx
from azure.identity import AzureCliCredential

_PREFIX = "PUBLICATION_AZURE_DEVOPS_"


def _config() -> dict[str, str] | None:
    names = (
        "BACKEND_URL",
        "API_SCOPE",
        "AREA_ID",
        "CHANGESET_ID",
        "REVISION",
        "CONTENT_HASH",
        "ORGANIZATION",
        "PROJECT",
        "REPOSITORY",
        "RUN_ID",
    )
    values = {name: os.environ.get(f"{_PREFIX}{name}", "").strip() for name in names}
    if not all(values.values()) or not sys.stdin.isatty():
        return None
    UUID(values["AREA_ID"])
    UUID(values["CHANGESET_ID"])
    if not values["REVISION"].isdigit() or int(values["REVISION"]) < 1:
        raise ValueError("PUBLICATION_AZURE_DEVOPS_REVISION_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", values["CONTENT_HASH"]):
        raise ValueError("PUBLICATION_AZURE_DEVOPS_CONTENT_HASH_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", values["RUN_ID"]):
        raise ValueError("PUBLICATION_AZURE_DEVOPS_RUN_ID_INVALID")
    return values


def _json(response: httpx.Response, expected: set[int]) -> dict[str, Any]:
    if response.status_code not in expected:
        raise AssertionError(
            f"HTTP_{response.status_code}: {response.text[:500]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("PUBLICATION_AZURE_DEVOPS_RESPONSE_INVALID")
    return payload


def _approve(client: httpx.Client, publication_id: str, approval: dict[str, Any]) -> dict[str, Any]:
    tool = str(approval.get("tool") or "")
    arguments = approval.get("arguments")
    print(f"\nTool: {tool}\nArguments: {arguments}")
    approved = input("Type 'approve' to execute this call: ").strip() == "approve"
    if not approved:
        raise AssertionError("PUBLICATION_AZURE_DEVOPS_APPROVAL_REJECTED")
    response = client.post(
        f"/authoring/publications/{publication_id}/approvals",
        json={"approval_id": approval["id"], "approved": True},
    )
    return _json(response, {200, 202})


def _run(config: dict[str, str]) -> None:
    credential = AzureCliCredential()
    token = credential.get_token(config["API_SCOPE"])
    headers = {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"azure-devops-smoke-{config['RUN_ID']}",
        "X-Area-ID": config["AREA_ID"],
    }
    body = {
        "provider": "azure_devops",
        "changeset_id": config["CHANGESET_ID"],
        "revision": int(config["REVISION"]),
        "content_hash": config["CONTENT_HASH"],
        "owner": config["ORGANIZATION"],
        "project": config["PROJECT"],
        "repository": config["REPOSITORY"],
        "base_branch": os.environ.get(
            f"{_PREFIX}BASE_BRANCH", "main"
        ).strip() or "main",
        "target_directory": os.environ.get(
            f"{_PREFIX}TARGET_DIRECTORY", "okf"
        ).strip() or "okf",
    }

    with httpx.Client(
        base_url=config["BACKEND_URL"].rstrip("/"), headers=headers, timeout=60.0
    ) as client:
        created = _json(client.post("/authoring/publications", json=body), {202})
        publication = created["publication"]
        publication_id = publication["id"]
        tools: list[str] = []
        outcome = created
        for _ in range(8):
            if outcome["publication"]["state"] == "completed":
                break
            approval = outcome.get("approval")
            if not isinstance(approval, dict):
                raise TypeError("PUBLICATION_AZURE_DEVOPS_APPROVAL_MISSING")
            tools.append(str(approval.get("tool") or ""))
            outcome = _approve(client, publication_id, approval)
        else:
            raise AssertionError("PUBLICATION_AZURE_DEVOPS_DID_NOT_COMPLETE")

        completed = outcome["publication"]
        assert completed["pull_request_url"], "PUBLICATION_AZURE_DEVOPS_PR_MISSING"
        assert completed["branch"], "PUBLICATION_AZURE_DEVOPS_BRANCH_MISSING"
        assert any(tool.endswith("find_pull_request") for tool in tools)
        assert any(tool.endswith("read_pull_request") for tool in tools)

        replay_response = client.post("/authoring/publications", json=body)
        replay = _json(replay_response, {200})
        assert replay_response.headers.get("Idempotent-Replay") == "true"
        assert replay["publication"]["id"] == publication_id
        assert replay["publication"]["pull_request_url"] == completed["pull_request_url"]

        read = _json(client.get(f"/authoring/publications/{publication_id}"), {200})
        assert read["state"] == "completed"
        assert read["pull_request_url"] == completed["pull_request_url"]
        assert "merge_status" in read
        print(f"Azure DevOps publication smoke: PASS ({read['pull_request_url']})")


def main() -> int:
    config = _config()
    if config is None:
        print(
            "Azure DevOps publication smoke skipped: set BACKEND_URL, API_SCOPE, "
            "AREA_ID, CHANGESET_ID, REVISION, CONTENT_HASH, ORGANIZATION, PROJECT, "
            f"REPOSITORY and RUN_ID with the {_PREFIX} prefix, then run from an "
            "interactive terminal after az login."
        )
        return 0
    _run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
