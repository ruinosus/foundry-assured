"""Smoke autenticado da reconciliação e materialização pós-merge.

Requer as variáveis PUBLICATION_MATERIALIZATION_* listadas em `_config`, uma
publicação em `pr_open` cujo PR já foi integrado e `az login` do Approver. O
smoke usa a API do produto; credenciais de Foundry/Search permanecem no backend.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any
from uuid import UUID

import httpx
from azure.identity import AzureCliCredential

_PREFIX = "PUBLICATION_MATERIALIZATION_"
_DEFAULT_KINDS = frozenset({"agent", "skill", "toolbox"})


def _config() -> dict[str, str] | None:
    names = ("BACKEND_URL", "API_SCOPE", "AREA_ID", "PUBLICATION_ID", "RUN_ID")
    values = {name: os.environ.get(f"{_PREFIX}{name}", "").strip() for name in names}
    if not all(values.values()) or not sys.stdin.isatty():
        return None
    UUID(values["AREA_ID"])
    UUID(values["PUBLICATION_ID"])
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", values["RUN_ID"]):
        raise ValueError("PUBLICATION_MATERIALIZATION_RUN_ID_INVALID")
    return values


def _json(response: httpx.Response, expected: set[int]) -> dict[str, Any]:
    if response.status_code not in expected:
        raise AssertionError(f"HTTP_{response.status_code}: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("PUBLICATION_MATERIALIZATION_RESPONSE_INVALID")
    return payload


def _expected_kinds() -> frozenset[str]:
    configured = os.environ.get(f"{_PREFIX}EXPECTED_KINDS", "").strip()
    kinds = frozenset(item.strip() for item in configured.split(",") if item.strip())
    expected = kinds or _DEFAULT_KINDS
    if not expected <= _DEFAULT_KINDS:
        raise ValueError("PUBLICATION_MATERIALIZATION_EXPECTED_KINDS_INVALID")
    return expected


def _assert_materialized(payload: dict[str, Any], expected_kinds: frozenset[str]) -> None:
    publication = payload.get("publication", payload)
    journal = payload.get("journal")
    if not isinstance(publication, dict) or not isinstance(journal, list):
        raise TypeError("PUBLICATION_MATERIALIZATION_RESPONSE_INVALID")
    assert publication.get("state") == "completed"
    assert publication.get("merge_status") == "merged"
    assert str(publication.get("commit_id") or "").strip()
    by_kind = {
        str(entry.get("kind")): entry
        for entry in journal
        if isinstance(entry, dict) and entry.get("kind") in expected_kinds
    }
    assert set(by_kind) == set(expected_kinds), "PUBLICATION_MATERIALIZATION_KIND_MISSING"
    for entry in by_kind.values():
        assert entry.get("status") == "completed"
        assert str(entry.get("external_id") or "").strip()


def _run(config: dict[str, str]) -> None:
    token = AzureCliCredential().get_token(config["API_SCOPE"])
    headers = {
        "Authorization": f"Bearer {token.token}",
        "X-Area-ID": config["AREA_ID"],
    }
    publication_path = f"/authoring/publications/{config['PUBLICATION_ID']}"
    with httpx.Client(
        base_url=config["BACKEND_URL"].rstrip("/"), headers=headers, timeout=90.0
    ) as client:
        current_response = client.get(publication_path)
        current = _json(current_response, {200})
        if current.get("state") != "pr_open":
            raise AssertionError("PUBLICATION_MATERIALIZATION_PR_NOT_OPEN")
        print(
            f"Publication: {current.get('pull_request_url')}\n"
            f"Approved hash: {current.get('content_hash')}"
        )
        if input("Type 'reconcile' after confirming the PR merge: ").strip() != "reconcile":
            raise AssertionError("PUBLICATION_MATERIALIZATION_NOT_APPROVED")
        request_headers = {
            "Idempotency-Key": f"materialize-{config['RUN_ID']}",
            "If-Match": current_response.headers["ETag"],
        }
        reconciled_response = client.post(
            f"{publication_path}/reconcile", headers=request_headers
        )
        reconciled = _json(reconciled_response, {200})
        expected_kinds = _expected_kinds()
        _assert_materialized(reconciled, expected_kinds)

        replay_headers = {
            "Idempotency-Key": f"materialize-{config['RUN_ID']}",
            "If-Match": reconciled_response.headers["ETag"],
        }
        replay = _json(client.post(f"{publication_path}/reconcile", headers=replay_headers), {200})
        _assert_materialized(replay, expected_kinds)
        assert replay["journal"] == reconciled["journal"], "PUBLICATION_MATERIALIZATION_REPLAY_DIVERGED"
        print(f"Materialization smoke: PASS ({config['PUBLICATION_ID']})")


def main() -> int:
    config = _config()
    if config is None:
        print(
            "Materialization smoke skipped: set BACKEND_URL, API_SCOPE, AREA_ID, "
            f"PUBLICATION_ID and RUN_ID with the {_PREFIX} prefix, then run from an "
            "interactive terminal after az login and merge the approved PR."
        )
        return 0
    _run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
