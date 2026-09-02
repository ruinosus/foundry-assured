"""Publicação Azure DevOps via OBO e Git REST API 7.1."""

from __future__ import annotations

import asyncio
import inspect
import json
import random
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
from azure.core.exceptions import ClientAuthenticationError

from app.modules.publication.internal.github import (
    GitHubPublicationService,
    PublicationConflict,
    PublicationExternalError,
    PublicationOutcome,
    SQLitePublicationRepository,
    StoredPublication,
    ToolApprovalRequest,
    _files,
)
from app.modules.publication.internal.reconciliation import (
    MergeEvidence,
    ReconciliationBlocked,
)

AZURE_DEVOPS_PERMISSION = "vso.code_write"
AZURE_DEVOPS_TOKEN_SCOPE = "499b84ac-1321-427f-aa17-267ca6975798/.default"
_API_VERSION = "7.1"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$", re.ASCII)
_REF = re.compile(
    r"^refs/heads/(?![./])(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]{1,128}$",
    re.ASCII,
)
_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$", re.ASCII)
_WRITE_TOOLS = frozenset({"push", "create_pull_request"})
_READ_TOOLS = frozenset({"get_ref", "find_pull_request", "read_pull_request"})
_TOOLS = _WRITE_TOOLS | _READ_TOOLS
_MAX_FILE_BYTES = 256 * 1024
_MAX_PUBLICATION_BYTES = 1024 * 1024


class AzureDevOpsAuthenticationRequired(PublicationExternalError):
    def __init__(self, claims: str) -> None:
        super().__init__("PUBLICATION_AZURE_DEVOPS_AUTHENTICATION_REQUIRED")
        self.claims = claims


@dataclass(frozen=True, slots=True)
class _PendingRequest:
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AzureDevOpsPublicationRequest:
    changeset_id: str
    revision: int
    content_hash: str
    organization: str
    project: str
    repository: str
    base_branch: str
    target_directory: str
    idempotency_key: str
    provider: str = "azure_devops"

    def __post_init__(self) -> None:
        _name(self.organization, "PUBLICATION_ORGANIZATION_INVALID")
        _name(self.project, "PUBLICATION_PROJECT_INVALID")
        _name(self.repository, "PUBLICATION_REPOSITORY_INVALID")
        _ref(f"refs/heads/{self.base_branch}")
        if not isinstance(self.revision, int) or self.revision < 1:
            raise PublicationConflict("PUBLICATION_REVISION_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise PublicationConflict("PUBLICATION_CONTENT_HASH_INVALID")
        if not 8 <= len(self.idempotency_key) <= 128:
            raise PublicationConflict("PUBLICATION_IDEMPOTENCY_KEY_INVALID")
        if not _PATH.fullmatch(self.target_directory) or ".." in self.target_directory.split("/"):
            raise PublicationConflict("PUBLICATION_TARGET_DIRECTORY_INVALID")

    @property
    def owner(self) -> str:
        return self.organization

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _name(value: Any, error: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise PublicationConflict(error)
    return value


def _ref(value: Any) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise PublicationConflict("PUBLICATION_REF_INVALID")
    return value


def _object_id(value: Any) -> str:
    if not isinstance(value, str) or not _OBJECT_ID.fullmatch(value):
        raise PublicationConflict("PUBLICATION_OBJECT_ID_INVALID")
    return value


def _change(value: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(value, Mapping):
        raise PublicationConflict("PUBLICATION_CHANGE_INVALID")
    change_type = value.get("change_type")
    path = value.get("path")
    if change_type not in {"add", "edit", "delete"}:
        raise PublicationConflict("PUBLICATION_CHANGE_TYPE_INVALID")
    if not isinstance(path, str) or not _PATH.fullmatch(path) or ".." in path.split("/"):
        raise PublicationConflict("PUBLICATION_DOCUMENT_PATH_INVALID")
    item: dict[str, Any] = {
        "changeType": change_type,
        "item": {"path": f"/{path}"},
    }
    if change_type == "delete":
        return item, 0
    content = value.get("content")
    if not isinstance(content, str):
        raise PublicationConflict("PUBLICATION_DOCUMENT_INVALID")
    size = len(content.encode("utf-8"))
    if size > _MAX_FILE_BYTES:
        raise PublicationConflict("PUBLICATION_DOCUMENT_TOO_LARGE")
    item["newContent"] = {"content": content, "contentType": "rawtext"}
    return item, size


def _changes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise PublicationConflict("PUBLICATION_DOCUMENTS_REQUIRED")
    parsed = [_change(change) for change in value]
    total_bytes = sum(size for _, size in parsed)
    if total_bytes > _MAX_PUBLICATION_BYTES:
        raise PublicationConflict("PUBLICATION_TOO_LARGE")
    return [change for change, _ in parsed]


class AzureDevOpsRestGateway:
    """Gateway com aprovação explícita; o token delegado só existe durante o egress."""

    def __init__(
        self,
        *,
        credential_factory: Callable[[], Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._credential_factory = credential_factory
        self._transport = transport
        self._pending: dict[str, _PendingRequest] = {}

    async def request_approval(
        self, tool: str, arguments: dict[str, Any]
    ) -> ToolApprovalRequest:
        await asyncio.sleep(0)
        if tool not in _TOOLS:
            raise PublicationExternalError("PUBLICATION_TOOL_NOT_ALLOWED")
        validated = self._validate(tool, arguments)
        approval_id = uuid4().hex
        self._pending[approval_id] = _PendingRequest(tool, validated)
        return ToolApprovalRequest(
            approval_id, f"azuredevops.{tool}", dict(validated)
        )

    async def decide(self, approval_id: str, *, approved: bool) -> Any:
        pending = self._pending.get(approval_id)
        if pending is None:
            raise PublicationExternalError("PUBLICATION_APPROVAL_NOT_FOUND")
        if not approved:
            self._pending.pop(approval_id, None)
            raise PublicationExternalError("PUBLICATION_APPROVAL_REJECTED")
        try:
            result = await self._execute(pending.tool, pending.arguments)
        except AzureDevOpsAuthenticationRequired:
            raise
        except Exception:
            self._pending.pop(approval_id, None)
            raise
        self._pending.pop(approval_id, None)
        return result

    async def execute_read(self, tool: str, arguments: dict[str, Any]) -> Any:
        if tool not in _READ_TOOLS:
            raise PublicationExternalError("PUBLICATION_TOOL_NOT_ALLOWED")
        return await self._execute(tool, self._validate(tool, arguments))

    @staticmethod
    def _validate(tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = {
            "organization": _name(
                arguments.get("organization"), "PUBLICATION_ORGANIZATION_INVALID"
            ),
            "project": _name(arguments.get("project"), "PUBLICATION_PROJECT_INVALID"),
            "repository": _name(
                arguments.get("repository"), "PUBLICATION_REPOSITORY_INVALID"
            ),
        }
        if tool in {"get_ref", "find_pull_request", "read_pull_request", "push", "create_pull_request"}:
            result["source_ref"] = _ref(arguments.get("source_ref"))
        if tool in {"find_pull_request", "read_pull_request", "create_pull_request"}:
            result["target_ref"] = _ref(arguments.get("target_ref"))
        if tool == "push":
            result["old_object_id"] = _object_id(arguments.get("old_object_id"))
            result["message"] = str(arguments.get("message") or "")[:256]
            if not result["message"]:
                raise PublicationConflict("PUBLICATION_COMMIT_MESSAGE_INVALID")
            result["changes"] = _changes(arguments.get("changes"))
        if tool == "create_pull_request":
            result["title"] = str(arguments.get("title") or "")[:256]
            result["description"] = str(arguments.get("description") or "")[:4096]
            if not result["title"]:
                raise PublicationConflict("PUBLICATION_PR_TITLE_INVALID")
        if tool == "read_pull_request":
            pull_request_id = arguments.get("pull_request_id")
            if not isinstance(pull_request_id, int) or pull_request_id < 1:
                raise PublicationConflict("PUBLICATION_PR_ID_INVALID")
            result["pull_request_id"] = pull_request_id
        return result

    async def _execute(self, tool: str, arguments: dict[str, Any]) -> Any:
        credential = (
            self._credential_factory or self._default_credential_factory()
        )()
        try:
            try:
                token = credential.get_token(AZURE_DEVOPS_TOKEN_SCOPE)
                if inspect.isawaitable(token):
                    token = await token
            except ClientAuthenticationError as exc:
                claims = self._claims_challenge(exc)
                if claims is not None:
                    raise AzureDevOpsAuthenticationRequired(claims) from exc
                raise PublicationExternalError(
                    "PUBLICATION_AZURE_DEVOPS_AUTHENTICATION_FAILED"
                ) from exc
            base_url = f"https://dev.azure.com/{quote(arguments['organization'], safe='')}"
            async with httpx.AsyncClient(
                base_url=base_url,
                headers={"Authorization": f"Bearer {token.token}"},
                timeout=30.0,
                transport=self._transport,
            ) as client:
                return await self._request(client, tool, arguments)
        finally:
            close = getattr(credential, "close", None)
            if callable(close):
                closed = close()
                if inspect.isawaitable(closed):
                    await closed

    @staticmethod
    def _claims_challenge(error: ClientAuthenticationError) -> str | None:
        response = error.response
        try:
            payload = response.json() if response is not None else None
        except (TypeError, ValueError):
            return None
        claims = payload.get("claims") if isinstance(payload, Mapping) else None
        if not isinstance(claims, str) or len(claims) > 8192 or "\r" in claims or "\n" in claims:
            return None
        try:
            parsed = json.loads(claims)
        except json.JSONDecodeError:
            return None
        return claims if isinstance(parsed, Mapping) else None

    @staticmethod
    def _default_credential_factory() -> Callable[[], Any]:
        from app.shared.auth import credential_for_request

        return credential_for_request

    async def _request(
        self, client: httpx.AsyncClient, tool: str, arguments: dict[str, Any]
    ) -> Any:
        handlers = {
            "get_ref": self._get_ref,
            "find_pull_request": self._find_pull_request,
            "push": self._push,
            "create_pull_request": self._create_pull_request,
            "read_pull_request": self._read_pull_request,
        }
        handler = handlers.get(tool)
        if handler is None:
            raise PublicationExternalError("PUBLICATION_TOOL_NOT_IMPLEMENTED")
        return await handler(client, arguments)

    @staticmethod
    def _root(arguments: Mapping[str, Any]) -> str:
        project = quote(arguments["project"], safe="")
        repository = quote(arguments["repository"], safe="")
        return f"/{project}/_apis/git/repositories/{repository}"

    async def _get_ref(self, client, arguments):
        response = await self._send(
            client,
            "GET",
            f"{self._root(arguments)}/refs",
            read=True,
            params={
                "filter": arguments["source_ref"].removeprefix("refs/"),
                "api-version": _API_VERSION,
            },
        )
        payload = self._json(response)
        refs = payload.get("value") if isinstance(payload, Mapping) else None
        matches = [
            item
            for item in refs or []
            if isinstance(item, Mapping)
            and item.get("name") == arguments["source_ref"]
            and isinstance(item.get("objectId"), str)
            and _OBJECT_ID.fullmatch(item["objectId"])
        ]
        if len(matches) != 1:
            raise PublicationExternalError("PUBLICATION_REF_NOT_FOUND")
        return {"source_ref": arguments["source_ref"], "object_id": matches[0]["objectId"]}

    async def _find_pull_request(self, client, arguments):
        response = await self._send(
            client,
            "GET",
            f"{self._root(arguments)}/pullrequests",
            read=True,
            params={
                "searchCriteria.sourceRefName": arguments["source_ref"],
                "searchCriteria.targetRefName": arguments["target_ref"],
                "searchCriteria.status": "all",
                "api-version": _API_VERSION,
            },
        )
        payload = self._json(response)
        values = payload.get("value") if isinstance(payload, Mapping) else None
        matches = [
            self._pull_request(item, arguments)
            for item in values or []
            if isinstance(item, Mapping)
            and item.get("sourceRefName") == arguments["source_ref"]
            and item.get("targetRefName") == arguments["target_ref"]
        ]
        if len(matches) > 1:
            raise PublicationConflict("PUBLICATION_PR_AMBIGUOUS")
        return matches[0] if matches else {"found": False}

    async def _push(self, client, arguments):
        response = await self._send(
            client,
            "POST",
            f"{self._root(arguments)}/pushes",
            read=False,
            params={"api-version": _API_VERSION},
            json={
                "refUpdates": [{"name": arguments["source_ref"], "oldObjectId": arguments["old_object_id"]}],
                "commits": [{"comment": arguments["message"], "changes": arguments["changes"]}],
            },
        )
        return self._push_result(response, arguments)

    async def _create_pull_request(self, client, arguments):
        response = await self._send(
            client,
            "POST",
            f"{self._root(arguments)}/pullrequests",
            read=False,
            params={"api-version": _API_VERSION},
            json={
                "sourceRefName": arguments["source_ref"],
                "targetRefName": arguments["target_ref"],
                "title": arguments["title"],
                "description": arguments["description"],
            },
        )
        return self._pull_request(self._json(response), arguments)

    async def _read_pull_request(self, client, arguments):
        response = await self._send(
            client,
            "GET",
            f"{self._root(arguments)}/pullrequests/{arguments['pull_request_id']}",
            read=True,
            params={"api-version": _API_VERSION},
        )
        return self._pull_request(self._json(response), arguments)

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        read: bool,
        **kwargs: Any,
    ) -> httpx.Response:
        attempts = 3 if read else 1
        for attempt in range(attempts):
            response = await self._request_attempt(
                client, method, url, attempt=attempt, attempts=attempts, **kwargs
            )
            if response is None:
                continue
            if self._transient(response) and attempt + 1 < attempts:
                await asyncio.sleep(self._retry_delay(response, attempt))
                continue
            self._raise_for_status(response)
            return response
        raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_TRANSIENT")

    @staticmethod
    async def _request_attempt(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        attempt: int,
        attempts: int,
        **kwargs: Any,
    ) -> httpx.Response | None:
        try:
            return await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt + 1 == attempts:
                raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_TRANSIENT") from exc
            await asyncio.sleep(AzureDevOpsRestGateway._backoff_delay(float(2**attempt)))
            return None

    @staticmethod
    def _transient(response: httpx.Response) -> bool:
        return response.status_code in {408, 429} or response.status_code >= 500

    @staticmethod
    def _retry_delay(
        response: httpx.Response,
        attempt: int,
        *,
        now: datetime | None = None,
    ) -> float:
        retry_after = response.headers.get("Retry-After")
        delay = AzureDevOpsRestGateway._retry_after_seconds(
            retry_after, now=now
        )
        if delay is None:
            delay = float(2**attempt)
        return AzureDevOpsRestGateway._backoff_delay(delay)

    @staticmethod
    def _retry_after_seconds(value: str | None, *, now: datetime | None) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        return max((retry_at - current).total_seconds(), 0.0)

    @staticmethod
    def _backoff_delay(delay: float) -> float:
        bounded = min(max(delay, 0.0), 30.0)
        jitter = random.uniform(0.0, min(bounded, 1.0))
        return min(bounded + jitter, 30.0)

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        if response.status_code in {409, 412}:
            raise PublicationConflict("PUBLICATION_REF_CONFLICT")
        if response.status_code in {401, 403}:
            raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_FORBIDDEN")
        if response.status_code == 404:
            raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_NOT_FOUND")
        if 400 <= response.status_code < 500:
            raise PublicationExternalError(
                f"PUBLICATION_AZURE_DEVOPS_HTTP_{response.status_code}"
            )
        if cls._transient(response):
            raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_TRANSIENT")

    @staticmethod
    def _json(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_RESULT_INVALID") from exc
        if not isinstance(payload, Mapping):
            raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_RESULT_INVALID")
        return payload

    @staticmethod
    def _pull_request(
        payload: Mapping[str, Any], arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        pull_request_id = payload.get("pullRequestId")
        repository = payload.get("repository")
        repository_name = repository.get("name") if isinstance(repository, Mapping) else None
        if (
            not isinstance(pull_request_id, int)
            or pull_request_id < 1
            or repository_name != arguments["repository"]
            or payload.get("sourceRefName") != arguments["source_ref"]
            or payload.get("targetRefName") != arguments["target_ref"]
        ):
            raise PublicationExternalError("PUBLICATION_PR_RESULT_INVALID")
        organization = quote(arguments["organization"], safe="")
        project = quote(arguments["project"], safe="")
        repo = quote(arguments["repository"], safe="")
        return {
            "found": True,
            "pull_request_id": pull_request_id,
            "pull_request_url": (
                f"https://dev.azure.com/{organization}/{project}/_git/{repo}"
                f"/pullrequest/{pull_request_id}"
            ),
            "source_ref": arguments["source_ref"],
            "target_ref": arguments["target_ref"],
            "status": str(payload.get("status") or ""),
            "merge_status": str(payload.get("mergeStatus") or ""),
            "description": str(payload.get("description") or ""),
            "merge_commit_id": str(
                (payload.get("lastMergeCommit") or {}).get("commitId")
                if isinstance(payload.get("lastMergeCommit"), Mapping)
                else ""
            ),
        }

    @staticmethod
    def _push_result(
        response: httpx.Response, arguments: Mapping[str, Any]
    ) -> dict[str, str]:
        if response.status_code in {409, 412}:
            raise PublicationConflict("PUBLICATION_REF_CONFLICT")
        if 400 <= response.status_code < 500:
            raise PublicationExternalError(
                f"PUBLICATION_AZURE_DEVOPS_HTTP_{response.status_code}"
            )
        if response.status_code >= 500:
            raise PublicationExternalError("PUBLICATION_AZURE_DEVOPS_TRANSIENT")
        try:
            payload = response.json()
            commit_id = payload["commits"][0]["commitId"]
            ref_update = payload["refUpdates"][0]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise PublicationExternalError("PUBLICATION_PUSH_RESULT_INVALID") from exc
        if (
            not _OBJECT_ID.fullmatch(commit_id)
            or ref_update.get("name") != arguments["source_ref"]
            or ref_update.get("oldObjectId") != arguments["old_object_id"]
            or ref_update.get("newObjectId") != commit_id
        ):
            raise PublicationExternalError("PUBLICATION_PUSH_RESULT_INVALID")
        return {
            "commit_id": commit_id,
            "source_ref": arguments["source_ref"],
        }


class AzureDevOpsPublicationService(GitHubPublicationService):
    @staticmethod
    def _arguments(
        publication: StoredPublication, files: list[dict[str, str]]
    ) -> tuple[str, dict[str, Any]]:
        common = {
            "organization": publication.owner,
            "project": publication.project,
            "repository": publication.repository,
        }
        source_ref = f"refs/heads/{publication.branch}"
        target_ref = f"refs/heads/{publication.base_branch}"
        if publication.step == "search":
            return "find_pull_request", {
                **common,
                "source_ref": source_ref,
                "target_ref": target_ref,
            }
        if publication.step == "branch":
            return "get_ref", {**common, "source_ref": target_ref}
        if publication.step == "push":
            return "push", {
                **common,
                "source_ref": source_ref,
                "old_object_id": publication.base_object_id,
                "message": f"Publish approved ChangeSet {publication.changeset_id}",
                "changes": [
                    {"change_type": "add", **file}
                    for file in files
                ],
            }
        if publication.step == "pull_request":
            return "create_pull_request", {
                **common,
                "source_ref": source_ref,
                "target_ref": target_ref,
                "title": f"Publish approved ChangeSet {publication.changeset_id[:8]}",
                "description": (
                    f"Revision {publication.revision}\n\n"
                    f"Content-SHA256: `{publication.content_hash}`"
                ),
            }
        if publication.step == "verify" and publication.pull_request_number > 0:
            return "read_pull_request", {
                **common,
                "source_ref": source_ref,
                "target_ref": target_ref,
                "pull_request_id": publication.pull_request_number,
            }
        raise PublicationConflict("PUBLICATION_STEP_INVALID")

    async def decide(
        self,
        scope,
        publication_id: str,
        approval_id: str,
        *,
        approved: bool,
        roles: set[str],
    ) -> PublicationOutcome:
        publication = self.get(scope, publication_id)
        self._assert_current(scope, publication, roles=roles)
        if publication.state != "awaiting_approval" or publication.approval_id != approval_id:
            raise PublicationConflict("PUBLICATION_APPROVAL_STALE")
        changeset = self._changesets.get(scope, publication.changeset_id)
        tool, _ = self._arguments(
            publication, _files(changeset.content, publication.target_directory)
        )
        if approved:
            publication = self._repository.begin_execution(
                scope,
                publication.id,
                approval_id,
                now=datetime.now(UTC).isoformat(),
            )
        try:
            result = await self._gateway.decide(approval_id, approved=approved)
            if not approved:
                raise PublicationExternalError("PUBLICATION_APPROVAL_REJECTED")
            transitioned = self._transition(scope, publication, approval_id, result)
        except PublicationConflict:
            self._repository.require_intervention(
                scope,
                publication.id,
                error_code="PUBLICATION_REF_CONFLICT",
                now=datetime.now(UTC).isoformat(),
            )
            raise
        except AzureDevOpsAuthenticationRequired:
            self._repository.restore_approval(
                scope,
                publication.id,
                approval_id,
                now=datetime.now(UTC).isoformat(),
            )
            raise
        except Exception as exc:
            self._record_failure(scope, publication, approved=approved, tool=tool, error=exc)
            if isinstance(exc, PublicationExternalError):
                raise
            raise PublicationExternalError("PUBLICATION_EXTERNAL_FAILURE") from exc
        if isinstance(transitioned, PublicationOutcome):
            return transitioned
        return await self._prepare(scope, transitioned, roles=roles)

    def _transition(
        self,
        scope,
        publication: StoredPublication,
        approval_id: str,
        result: Mapping[str, Any],
    ) -> StoredPublication | PublicationOutcome:
        if publication.step == "verify":
            return self._complete(scope, publication, result)
        next_step, number, url, base_object_id, commit_id = self._next_state(
            publication, result
        )
        return self._repository.advance(
            scope,
            publication.id,
            approval_id,
            next_step=next_step,
            pull_request_number=number,
            pull_request_url=url,
            base_object_id=base_object_id,
            commit_id=commit_id,
            now=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _next_state(
        publication: StoredPublication, result: Mapping[str, Any]
    ) -> tuple[str, int, str, str, str]:
        number = publication.pull_request_number
        url = publication.pull_request_url
        if publication.step == "search":
            if result.get("found"):
                return "verify", result["pull_request_id"], result["pull_request_url"], "", ""
            return "branch", number, url, "", ""
        if publication.step == "branch":
            return "push", number, url, result["object_id"], ""
        if publication.step == "push":
            return "pull_request", number, url, "", result["commit_id"]
        if publication.step == "pull_request":
            return "verify", result["pull_request_id"], result["pull_request_url"], "", ""
        raise PublicationConflict("PUBLICATION_STEP_INVALID")

    def _complete(
        self, scope, publication: StoredPublication, result: Mapping[str, Any]
    ) -> PublicationOutcome:
        if (
            result.get("pull_request_id") != publication.pull_request_number
            or result.get("pull_request_url") != publication.pull_request_url
        ):
            raise PublicationExternalError("PUBLICATION_PR_VERIFICATION_FAILED")
        completed = self._repository.complete(
            scope,
            publication.id,
            pull_request_number=publication.pull_request_number,
            pull_request_url=publication.pull_request_url,
            merge_status=result.get("merge_status", ""),
            now=datetime.now(UTC).isoformat(),
        )
        return PublicationOutcome(completed, None, False)

    def _record_failure(
        self,
        scope,
        publication: StoredPublication,
        *,
        approved: bool,
        tool: str,
        error: Exception,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        if approved and tool in _WRITE_TOOLS:
            self._repository.require_intervention(
                scope,
                publication.id,
                error_code="PUBLICATION_WRITE_OUTCOME_UNKNOWN",
                now=now,
            )
            return
        self._repository.fail(
            scope, publication.id, error_code=str(error), now=now
        )

    async def reconcile(
        self, scope, publication_id: str, *, roles: set[str], expected_etag: str
    ):
        publication = self.get(scope, publication_id)
        if publication.etag != expected_etag:
            raise PublicationConflict("PUBLICATION_REVISION_STALE")
        changeset = self._assert_current(scope, publication, roles=roles)
        if self._reconciler is None:
            raise PublicationExternalError("PUBLICATION_RECONCILIATION_NOT_CONFIGURED")
        if publication.state == "completed":
            return publication, self._reconciler.journal(scope, publication.id)
        if publication.state not in {"pr_open", "materializing"}:
            raise PublicationConflict("PUBLICATION_STATE_INVALID")
        arguments = {
            "organization": publication.owner,
            "project": publication.project,
            "repository": publication.repository,
            "source_ref": f"refs/heads/{publication.branch}",
            "target_ref": f"refs/heads/{publication.base_branch}",
            "pull_request_id": publication.pull_request_number,
        }
        result = await self._gateway.execute_read("read_pull_request", arguments)
        description = str(result.get("description") or "")
        match = re.search(r"Content-SHA256:\s*`([0-9a-f]{64})`", description)
        evidence = MergeEvidence(
            merged=result.get("status") == "completed",
            commit_id=str(result.get("merge_commit_id") or ""),
            content_hash=match.group(1) if match else "",
        )
        try:
            reconciled = self._reconciler.reconcile(
                publication, evidence, scope=scope,
                operations=changeset.content["operations"],
            )
        except Exception as exc:
            if isinstance(exc, ReconciliationBlocked):
                raise PublicationConflict(str(exc)) from exc
            raise
        return self.get(scope, publication.id), reconciled.journal

    def journal(self, scope, publication_id: str):
        publication = self.get(scope, publication_id)
        if self._reconciler is None:
            return ()
        return self._reconciler.journal(scope, publication.id)


_default_service: AzureDevOpsPublicationService | None = None


def default_azure_devops_publication_service() -> AzureDevOpsPublicationService:
    global _default_service
    if _default_service is None:
        import app
        from app.modules.authoring.public import (
            default_changeset_service,
            default_decision_service,
        )

        data_directory = Path(app.__file__).resolve().parent.parent / "data"
        database = data_directory / "authoring.sqlite3"
        repository = SQLitePublicationRepository(database)
        from app.modules.publication.internal.reconciliation import (
            OfficialFoundryMaterializer,
            ReconciliationService,
            SQLiteMaterializationJournal,
        )

        _default_service = AzureDevOpsPublicationService(
            changesets=default_changeset_service(),
            decisions=default_decision_service(),
            repository=repository,
            gateway=AzureDevOpsRestGateway(),
            reconciler=ReconciliationService(
                OfficialFoundryMaterializer(),
                journal=SQLiteMaterializationJournal(database),
                publications=repository,
            ),
        )
    return _default_service


class PublicationServiceRouter:
    def __init__(
        self,
        github: GitHubPublicationService,
        azure_devops: AzureDevOpsPublicationService,
    ) -> None:
        self._github = github
        self._azure_devops = azure_devops

    async def publish(self, scope, request, *, roles: set[str]) -> PublicationOutcome:
        service = (
            self._azure_devops
            if isinstance(request, AzureDevOpsPublicationRequest)
            else self._github
        )
        return await service.publish(scope, request, roles=roles)

    def _service(self, scope, publication_id: str):
        publication = self._github.get(scope, publication_id)
        return self._azure_devops if publication.provider == "azure_devops" else self._github

    async def decide(
        self,
        scope,
        publication_id: str,
        approval_id: str,
        *,
        approved: bool,
        roles: set[str],
    ) -> PublicationOutcome:
        return await self._service(scope, publication_id).decide(
            scope,
            publication_id,
            approval_id,
            approved=approved,
            roles=roles,
        )

    def get(self, scope, publication_id: str) -> StoredPublication:
        return self._service(scope, publication_id).get(scope, publication_id)

    def journal(self, scope, publication_id: str):
        return self._service(scope, publication_id).journal(scope, publication_id)

    async def reconcile(
        self, scope, publication_id: str, *, roles: set[str], expected_etag: str
    ):
        return await self._service(scope, publication_id).reconcile(
            scope, publication_id, roles=roles, expected_etag=expected_etag
        )

    def compensate(
        self, scope, publication_id: str, *, roles: set[str], expected_etag: str
    ):
        return self._service(scope, publication_id).compensate(
            scope, publication_id, roles=roles, expected_etag=expected_etag
        )


def default_publication_router() -> PublicationServiceRouter:
    from app.modules.publication.internal.github import default_publication_service

    return PublicationServiceRouter(
        default_publication_service(), default_azure_devops_publication_service()
    )
