"""Publicação GitHub via Foundry Toolbox e servidor MCP oficial."""

from __future__ import annotations

import asyncio
import inspect
import json
import random
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

import rfc8785

import app
from app.modules.authoring.public import (
    ChangeSetScope,
    default_changeset_service,
    default_decision_service,
)
from app.modules.publication.internal.reconciliation import (
    MergeEvidence,
    ReconciliationBlocked,
)

if TYPE_CHECKING:
    from app.modules.authoring.public import ChangeSetService, DecisionService

_REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", re.ASCII)
_BRANCH = re.compile(
    r"^(?![./])(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]{1,128}$", re.ASCII
)
_DIRECTORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$", re.ASCII)
_MAX_FILE_BYTES = 256 * 1024
_MAX_PUBLICATION_BYTES = 1024 * 1024
_EMPTY_TEXT_COLUMN = "TEXT NOT NULL DEFAULT ''"
_TOOL_NAMESPACE = "foundrygithubmcp"
_TOOLS = frozenset(
    {
        "search_pull_requests",
        "create_branch",
        "push_files",
        "create_pull_request",
        "pull_request_read",
    }
)
_READ_TOOLS = frozenset({"search_pull_requests", "pull_request_read"})


class PublicationInvalid(ValueError):
    """A entrada de publicação não satisfaz o contrato público."""


class PublicationConflict(PublicationInvalid):
    """A publicação conflita com autorização, hash ou idempotência atuais."""


class PublicationNotFound(PublicationInvalid):
    """A publicação não existe no tenant e área consultados."""


class PublicationExternalError(RuntimeError):
    """A Toolbox não concluiu a operação externa."""


class PublicationConsentRequired(PublicationExternalError):
    """A conexão gerenciada exige consentimento OAuth do usuário atual."""

    def __init__(self, consent_url: str, server_label: str) -> None:
        super().__init__("PUBLICATION_CONSENT_REQUIRED")
        if not consent_url.startswith("https://"):
            raise PublicationExternalError("PUBLICATION_CONSENT_INVALID")
        self.consent_url = consent_url
        self.server_label = server_label


@dataclass(frozen=True, slots=True)
class PublicationRequest:
    changeset_id: str
    revision: int
    content_hash: str
    owner: str
    repository: str
    base_branch: str
    target_directory: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not _REPOSITORY.fullmatch(self.owner) or not _REPOSITORY.fullmatch(
            self.repository
        ):
            raise PublicationInvalid("PUBLICATION_REPOSITORY_INVALID")
        if not _BRANCH.fullmatch(self.base_branch) or self.base_branch.endswith(
            (".", "/")
        ):
            raise PublicationInvalid("PUBLICATION_BASE_BRANCH_INVALID")
        if (
            not _DIRECTORY.fullmatch(self.target_directory)
            or ".." in self.target_directory.split("/")
            or self.target_directory.endswith("/")
        ):
            raise PublicationInvalid("PUBLICATION_TARGET_DIRECTORY_INVALID")
        if not isinstance(self.revision, int) or self.revision < 1:
            raise PublicationInvalid("PUBLICATION_REVISION_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise PublicationInvalid("PUBLICATION_CONTENT_HASH_INVALID")
        if (
            not isinstance(self.idempotency_key, str)
            or not 8 <= len(self.idempotency_key) <= 128
        ):
            raise PublicationInvalid("PUBLICATION_IDEMPOTENCY_KEY_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StoredPublication:
    id: str
    changeset_id: str
    revision: int
    content_hash: str
    owner: str
    repository: str
    base_branch: str
    target_directory: str
    branch: str
    pull_request_number: int
    pull_request_url: str
    state: str
    step: str
    approval_id: str
    error_code: str
    created_at: str
    updated_at: str
    provider: str = "github"
    project: str = ""
    base_object_id: str = ""
    commit_id: str = ""
    merge_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "etag": self.etag}

    @property
    def etag(self) -> str:
        value = f"{self.id}:{self.state}:{self.step}:{self.updated_at}"
        return f'"{sha256(value.encode()).hexdigest()}"'


class PublicationGateway(Protocol):
    async def request_approval(
        self, tool: str, arguments: dict[str, Any]
    ) -> ToolApprovalRequest: ...

    async def execute_read(self, tool: str, arguments: dict[str, Any]) -> Any: ...

    async def decide(self, approval_id: str, *, approved: bool) -> Any: ...


@dataclass(frozen=True, slots=True)
class ToolApprovalRequest:
    id: str
    tool: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublicationOutcome:
    publication: StoredPublication
    approval: ToolApprovalRequest | None
    replay: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "publication": self.publication.to_dict(),
            "approval": self.approval.to_dict() if self.approval else None,
            "replay": self.replay,
        }


@dataclass(slots=True)
class _PendingToolApproval:
    agent: Any
    session: Any
    approval: Any
    client: Any
    exception_capture: Any
    toolbox: Any
    credential: Any


class SQLitePublicationRepository:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS github_publications (
                    tenant_id TEXT NOT NULL, area_id TEXT NOT NULL,
                    publication_id TEXT NOT NULL, changeset_id TEXT NOT NULL,
                    revision BIGINT NOT NULL, content_hash TEXT NOT NULL,
                    owner TEXT NOT NULL, repository TEXT NOT NULL,
                    base_branch TEXT NOT NULL, target_directory TEXT NOT NULL DEFAULT 'okf',
                    branch TEXT NOT NULL,
                    pull_request_number BIGINT NOT NULL,
                    pull_request_url TEXT NOT NULL, state TEXT NOT NULL,
                    step TEXT NOT NULL DEFAULT 'search',
                    approval_id TEXT NOT NULL DEFAULT '',
                    error_code TEXT NOT NULL DEFAULT '',
                    key_hash TEXT NOT NULL, request_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, area_id, publication_id),
                    UNIQUE (tenant_id, area_id, key_hash)
                )"""
            )
            connection.commit()
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(github_publications)")
            }
            if "error_code" not in columns:
                connection.execute(
                    "ALTER TABLE github_publications ADD COLUMN error_code TEXT NOT NULL DEFAULT ''"
                )
                connection.commit()
            for name, definition in (
                ("target_directory", "TEXT NOT NULL DEFAULT 'okf'"),
                ("step", "TEXT NOT NULL DEFAULT 'search'"),
                ("approval_id", _EMPTY_TEXT_COLUMN),
                ("provider", "TEXT NOT NULL DEFAULT 'github'"),
                ("project", _EMPTY_TEXT_COLUMN),
                ("base_object_id", _EMPTY_TEXT_COLUMN),
                ("commit_id", _EMPTY_TEXT_COLUMN),
                ("merge_status", _EMPTY_TEXT_COLUMN),
            ):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE github_publications ADD COLUMN {name} {definition}"
                    )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    @staticmethod
    def _record(row: tuple[Any, ...]) -> StoredPublication:
        return StoredPublication(
            id=row[0],
            changeset_id=row[1],
            revision=int(row[2]),
            content_hash=row[3],
            owner=row[4],
            repository=row[5],
            base_branch=row[6],
            target_directory=row[7],
            branch=row[8],
            pull_request_number=int(row[9]),
            pull_request_url=row[10],
            state=row[11],
            step=row[12],
            approval_id=row[13],
            error_code=row[14],
            created_at=row[15],
            updated_at=row[16],
            provider=row[17] if len(row) > 17 else "github",
            project=row[18] if len(row) > 18 else "",
            base_object_id=row[19] if len(row) > 19 else "",
            commit_id=row[20] if len(row) > 20 else "",
            merge_status=row[21] if len(row) > 21 else "",
        )

    def reserve(
        self,
        scope: ChangeSetScope,
        request: PublicationRequest,
        *,
        publication_id: str,
        branch: str,
        request_hash: str,
        now: str,
    ) -> tuple[StoredPublication | None, bool]:
        key_hash = sha256(request.idempotency_key.encode()).hexdigest()
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            existing = cursor.execute(
                """SELECT publication_id, changeset_id, revision, content_hash,
                          owner, repository, base_branch, target_directory, branch,
                          pull_request_number, pull_request_url, state, step, approval_id,
                         error_code, created_at, updated_at, provider, project,
                         base_object_id, commit_id, merge_status, request_hash
                   FROM github_publications
                   WHERE tenant_id = ? AND area_id = ? AND key_hash = ?""",
                (scope.tenant_id, scope.area_id, key_hash),
            ).fetchone()
            if existing is not None:
                if existing[22] != request_hash:
                    raise PublicationConflict("PUBLICATION_IDEMPOTENCY_KEY_REUSED")
                if existing[11] in {"pr_open", "completed"}:
                    connection.commit()
                    return self._record(existing[:22]), True
                if existing[11] in {
                    "in_progress",
                    "awaiting_approval",
                    "executing",
                    "intervention_required",
                }:
                    raise PublicationConflict("PUBLICATION_IN_PROGRESS")
                cursor.execute(
                    """UPDATE github_publications
                       SET state = 'in_progress', approval_id = '', error_code = '', updated_at = ?
                       WHERE tenant_id = ? AND area_id = ? AND publication_id = ?""",
                    (now, scope.tenant_id, scope.area_id, existing[0]),
                )
                connection.commit()
                return self._record(existing[:22]), False
            provider = getattr(request, "provider", "github")
            project = getattr(request, "project", "")
            cursor.execute(
                """INSERT INTO github_publications
                   (tenant_id, area_id, publication_id, changeset_id, revision,
                    content_hash, owner, repository, base_branch, target_directory, branch,
                    pull_request_number, pull_request_url, state, error_code, key_hash,
                    request_hash, created_at, updated_at, provider, project)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', 'in_progress', '', ?, ?, ?, ?, ?, ?)""",
                (
                    scope.tenant_id,
                    scope.area_id,
                    publication_id,
                    request.changeset_id,
                    request.revision,
                    request.content_hash,
                    request.owner,
                    request.repository,
                    request.base_branch,
                    request.target_directory,
                    branch,
                    key_hash,
                    request_hash,
                    now,
                    now,
                    provider,
                    project,
                ),
            )
            connection.commit()
            return None, False
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def await_approval(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        approval_id: str,
        *,
        now: str,
    ) -> StoredPublication:
        connection = self._connect()
        try:
            changed = connection.execute(
                """UPDATE github_publications
                   SET state = 'awaiting_approval', approval_id = ?, updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                                         AND state = 'in_progress'""",
                (approval_id, now, scope.tenant_id, scope.area_id, publication_id),
            ).rowcount
            if changed != 1:
                raise PublicationConflict("PUBLICATION_STATE_CONFLICT")
            connection.commit()
            result = self.get(scope, publication_id)
            if result is None:
                raise PublicationNotFound("PUBLICATION_NOT_FOUND")
            return result
        finally:
            connection.close()

    def advance(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        approval_id: str,
        *,
        next_step: str,
        pull_request_number: int = 0,
        pull_request_url: str = "",
        base_object_id: str = "",
        commit_id: str = "",
        now: str,
    ) -> StoredPublication:
        connection = self._connect()
        try:
            changed = connection.execute(
                """UPDATE github_publications
                   SET state = 'in_progress', step = ?, approval_id = '',
                       pull_request_number = CASE WHEN ? > 0 THEN ? ELSE pull_request_number END,
                       pull_request_url = CASE WHEN ? != '' THEN ? ELSE pull_request_url END,
                       base_object_id = CASE WHEN ? != '' THEN ? ELSE base_object_id END,
                       commit_id = CASE WHEN ? != '' THEN ? ELSE commit_id END,
                       updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                                         AND state = 'executing' AND approval_id = ?""",
                (
                    next_step,
                    pull_request_number,
                    pull_request_number,
                    pull_request_url,
                    pull_request_url,
                    base_object_id,
                    base_object_id,
                    commit_id,
                    commit_id,
                    now,
                    scope.tenant_id,
                    scope.area_id,
                    publication_id,
                    approval_id,
                ),
            ).rowcount
            if changed != 1:
                raise PublicationConflict("PUBLICATION_APPROVAL_STALE")
            connection.commit()
            result = self.get(scope, publication_id)
            if result is None:
                raise PublicationNotFound("PUBLICATION_NOT_FOUND")
            return result
        finally:
            connection.close()

    def begin_execution(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        approval_id: str,
        *,
        now: str,
    ) -> StoredPublication:
        connection = self._connect()
        try:
            changed = connection.execute(
                """UPDATE github_publications
                   SET state = 'executing', updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                     AND state = 'awaiting_approval' AND approval_id = ?""",
                (
                    now,
                    scope.tenant_id,
                    scope.area_id,
                    publication_id,
                    approval_id,
                ),
            ).rowcount
            if changed != 1:
                raise PublicationConflict("PUBLICATION_APPROVAL_STALE")
            connection.commit()
            result = self.get(scope, publication_id)
            if result is None:
                raise PublicationNotFound("PUBLICATION_NOT_FOUND")
            return result
        finally:
            connection.close()

    def restore_approval(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        approval_id: str,
        *,
        now: str,
    ) -> StoredPublication:
        connection = self._connect()
        try:
            changed = connection.execute(
                """UPDATE github_publications
                   SET state = 'awaiting_approval', updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                     AND state = 'executing' AND approval_id = ?""",
                (
                    now,
                    scope.tenant_id,
                    scope.area_id,
                    publication_id,
                    approval_id,
                ),
            ).rowcount
            if changed != 1:
                raise PublicationConflict("PUBLICATION_APPROVAL_STALE")
            connection.commit()
            result = self.get(scope, publication_id)
            if result is None:
                raise PublicationNotFound("PUBLICATION_NOT_FOUND")
            return result
        finally:
            connection.close()

    def require_intervention(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        *,
        error_code: str,
        now: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """UPDATE github_publications
                   SET state = 'intervention_required', error_code = ?, updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                     AND state = 'executing'""",
                (error_code, now, scope.tenant_id, scope.area_id, publication_id),
            )
            connection.commit()
        finally:
            connection.close()

    def complete(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        *,
        pull_request_number: int,
        pull_request_url: str,
        merge_status: str = "",
        now: str,
    ) -> StoredPublication:
        connection = self._connect()
        try:
            changed = connection.execute(
                """UPDATE github_publications
                   SET pull_request_number = ?, pull_request_url = ?, state = 'pr_open',
                       merge_status = ?, step = 'reconcile', approval_id = '', updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                                         AND state = 'executing'""",
                (
                    pull_request_number,
                    pull_request_url,
                    merge_status,
                    now,
                    scope.tenant_id,
                    scope.area_id,
                    publication_id,
                ),
            ).rowcount
            if changed != 1:
                raise PublicationConflict("PUBLICATION_STATE_CONFLICT")
            connection.commit()
            result = self.get(scope, publication_id)
            if result is None:
                raise PublicationNotFound("PUBLICATION_NOT_FOUND")
            return result
        finally:
            connection.close()

    def transition_reconciliation(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        *,
        expected_states: Sequence[str],
        state: str,
        step: str,
        commit_id: str = "",
        merge_status: str = "",
        error_code: str = "",
        now: str,
    ) -> StoredPublication:
        allowed = {
            "pr_open", "merge_confirmed", "materializing", "completed",
            "compensating", "compensated", "compensation_required",
        }
        if state not in allowed or not expected_states or not set(expected_states) <= allowed:
            raise PublicationConflict("PUBLICATION_STATE_INVALID")
        placeholders = ", ".join("?" for _ in expected_states)
        connection = self._connect()
        try:
            changed = connection.execute(
                f"""UPDATE github_publications
                    SET state = ?, step = ?,
                        commit_id = CASE WHEN ? != '' THEN ? ELSE commit_id END,
                        merge_status = CASE WHEN ? != '' THEN ? ELSE merge_status END,
                        error_code = ?, updated_at = ?
                    WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                      AND state IN ({placeholders})""",
                (
                    state, step, commit_id, commit_id, merge_status, merge_status,
                    error_code, now, scope.tenant_id, scope.area_id, publication_id,
                    *expected_states,
                ),
            ).rowcount
            if changed != 1:
                raise PublicationConflict("PUBLICATION_STATE_CONFLICT")
            connection.commit()
            result = self.get(scope, publication_id)
            if result is None:
                raise PublicationNotFound("PUBLICATION_NOT_FOUND")
            return result
        finally:
            connection.close()

    def fail(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        *,
        error_code: str,
        now: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """UPDATE github_publications
                   SET state = 'failed', error_code = ?, updated_at = ?
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?
                                         AND state IN ('in_progress', 'awaiting_approval', 'executing')""",
                (error_code, now, scope.tenant_id, scope.area_id, publication_id),
            )
            connection.commit()
        finally:
            connection.close()

    def get(
        self, scope: ChangeSetScope, publication_id: str
    ) -> StoredPublication | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """SELECT publication_id, changeset_id, revision, content_hash,
                          owner, repository, base_branch, target_directory, branch,
                          pull_request_number, pull_request_url, state, step, approval_id,
                         error_code, created_at, updated_at, provider, project,
                         base_object_id, commit_id, merge_status
                   FROM github_publications
                   WHERE tenant_id = ? AND area_id = ? AND publication_id = ?""",
                (scope.tenant_id, scope.area_id, publication_id),
            ).fetchone()
            return self._record(row) if row is not None else None
        finally:
            connection.close()


class FoundryToolboxGateway:
    def __init__(
        self,
        endpoint: str,
        credential_factory: Callable[[], Any] | None = None,
        toolbox_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._credential_factory = credential_factory
        self._toolbox_factory = toolbox_factory
        self._pending: dict[str, _PendingToolApproval] = {}

    @staticmethod
    def _function(toolbox: Any, tool: str) -> Any:
        qualified_name = f"{_TOOL_NAMESPACE}.{tool}"
        matches = [
            function
            for function in toolbox.functions
            if function.name == qualified_name
        ]
        if len(matches) != 1:
            raise PublicationExternalError("PUBLICATION_TOOL_NOT_AVAILABLE")
        function = matches[0]
        function.approval_mode = "always_require"
        return function

    @staticmethod
    async def _close(toolbox: Any, credential: Any) -> None:
        await toolbox.__aexit__(None, None, None)
        close = getattr(credential, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result

    @staticmethod
    def _raise_consent(exc: Exception) -> None:
        from agent_framework_foundry_hosting._responses import (  # pyright: ignore[reportPrivateUsage]
            consent_url_from_error,
        )

        consent = consent_url_from_error(exc) or consent_url_from_error(
            PublicationExternalError("PUBLICATION_MCP_FAILURE", exc)
        )
        if consent:
            raise PublicationConsentRequired(
                consent[0].consent_url, consent[0].name
            ) from exc

    @staticmethod
    def _retry_delay(exc: Exception, attempt: int) -> float | None:
        status = getattr(exc, "status_code", None)
        transient = isinstance(exc, (TimeoutError, ConnectionError)) or status in {
            408,
            429,
        }
        transient = transient or (isinstance(status, int) and 500 <= status < 600)
        if not transient:
            return None
        headers = getattr(exc, "headers", {}) or {}
        retry_after = headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), 30.0)
            except (TypeError, ValueError):
                pass
        base = float(2**attempt)
        return min(base + random.uniform(0.0, base * 0.25), 30.0)

    async def request_approval(
        self, tool: str, arguments: dict[str, Any]
    ) -> ToolApprovalRequest:
        if not self._endpoint.startswith("https://"):
            raise PublicationExternalError("PUBLICATION_TOOLBOX_NOT_CONFIGURED")
        if tool not in _TOOLS:
            raise PublicationExternalError("PUBLICATION_TOOL_NOT_ALLOWED")
        from agent_framework import (
            Agent,
            BaseChatClient,
            ChatResponse,
            Content,
            FunctionInvocationLayer,
            FunctionMiddleware,
            Message,
        )
        from agent_framework_foundry_hosting import FoundryToolbox

        from app.shared.auth import credential_for_request

        class _SingleToolClient(FunctionInvocationLayer, BaseChatClient):
            def __init__(
                self, function_name: str, function_arguments: dict[str, Any]
            ) -> None:
                super().__init__()
                self.function_name = function_name
                self.function_arguments = function_arguments
                self.called = False
                self.result: Any = None
                self.exception: Exception | None = None

            async def _inner_get_response(self, *, messages, stream, options, **kwargs):
                if stream:
                    raise PublicationExternalError("PUBLICATION_STREAM_UNSUPPORTED")
                for message in messages:
                    for content in message.contents:
                        if content.type == "function_result":
                            self.result = content.result
                            self.exception = content.exception
                if not self.called:
                    self.called = True
                    content = Content.from_function_call(
                        call_id=uuid4().hex,
                        name=self.function_name,
                        arguments=self.function_arguments,
                    )
                else:
                    content = Content.from_text("completed")
                return ChatResponse(
                    messages=[Message(role="assistant", contents=[content])]
                )

        class _ExceptionCapture(FunctionMiddleware):
            def __init__(self, retry_delay, *, allow_retry: bool) -> None:
                self.exception: Exception | None = None
                self._retry_delay = retry_delay
                self._allow_retry = allow_retry

            async def process(self, context, call_next) -> None:
                for attempt in range(3):
                    try:
                        await call_next()
                        return
                    except Exception as exc:
                        delay = (
                            self._retry_delay(exc, attempt)
                            if self._allow_retry
                            else None
                        )
                        if delay is None or attempt == 2:
                            self.exception = exc
                            raise
                        await asyncio.sleep(delay)

        credential = (self._credential_factory or credential_for_request)()
        factory = self._toolbox_factory or FoundryToolbox
        toolbox = factory(credential, url=self._endpoint, timeout=30.0)
        try:
            try:
                await toolbox.__aenter__()
                function = self._function(toolbox, tool)
                client = _SingleToolClient(function.name, arguments)
                exception_capture = _ExceptionCapture(
                    self._retry_delay, allow_retry=tool in _READ_TOOLS
                )
                agent = Agent(
                    client=client,
                    tools=[function],
                    middleware=[exception_capture],
                    default_options={"store": False},
                )
                session = agent.create_session()
                response = await asyncio.wait_for(
                    agent.run("prepare protected publication write", session=session),
                    timeout=30.0,
                )
                response_contents = [
                    content
                    for message in response.messages
                    for content in message.contents
                ]
                requests_by_id = {
                    content.id: content
                    for content in [*response.user_input_requests, *response_contents]
                    if content.type == "function_approval_request"
                }
                requests = list(requests_by_id.values())
                if len(requests) != 1:
                    raise PublicationExternalError("PUBLICATION_APPROVAL_NOT_EMITTED")
                approval_id = uuid4().hex
                self._pending[approval_id] = _PendingToolApproval(
                    agent=agent,
                    session=session,
                    approval=requests[0],
                    client=client,
                    exception_capture=exception_capture,
                    toolbox=toolbox,
                    credential=credential,
                )
                return ToolApprovalRequest(approval_id, function.name, dict(arguments))
            except Exception as exc:
                self._raise_consent(exc)
                raise
        except Exception:
            await self._close(toolbox, credential)
            raise

    async def decide(self, approval_id: str, *, approved: bool) -> Any:
        from agent_framework import Message

        pending = self._pending.pop(approval_id, None)
        if pending is None:
            raise PublicationExternalError("PUBLICATION_APPROVAL_NOT_FOUND")
        try:
            response = pending.approval.to_function_approval_response(approved=approved)
            await asyncio.wait_for(
                pending.agent.run(
                    Message(role="user", contents=[response]),
                    session=pending.session,
                ),
                timeout=30.0,
            )
            if not approved:
                raise PublicationExternalError("PUBLICATION_APPROVAL_REJECTED")
            if pending.exception_capture.exception is not None:
                raise pending.exception_capture.exception
            if pending.client.exception is not None:
                raise PublicationExternalError("PUBLICATION_TOOL_EXECUTION_FAILED")
            if pending.client.result is None:
                raise PublicationExternalError("PUBLICATION_TOOL_RESULT_MISSING")
            return pending.client.result
        except Exception as exc:
            self._raise_consent(exc)
            raise
        finally:
            await self._close(pending.toolbox, pending.credential)

    async def execute_read(self, tool: str, arguments: dict[str, Any]) -> Any:
        if tool not in _READ_TOOLS:
            raise PublicationExternalError("PUBLICATION_TOOL_NOT_ALLOWED")
        approval = await self.request_approval(tool, arguments)
        return await self.decide(approval.id, approved=True)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _files(content: Mapping[str, Any], target_directory: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    total_bytes = 0
    for operation in content["operations"]:
        raw = operation.get("document")
        if not isinstance(raw, str):
            continue
        document_type = str(operation.get("document_type") or "document")
        identifier = str(operation["id"])
        if not _REPOSITORY.fullmatch(document_type) or not _REPOSITORY.fullmatch(
            identifier
        ):
            raise PublicationInvalid("PUBLICATION_DOCUMENT_PATH_INVALID")
        normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
        file_bytes = len(normalized.encode("utf-8"))
        if file_bytes > _MAX_FILE_BYTES:
            raise PublicationInvalid("PUBLICATION_DOCUMENT_TOO_LARGE")
        total_bytes += file_bytes
        if total_bytes > _MAX_PUBLICATION_BYTES:
            raise PublicationInvalid("PUBLICATION_TOO_LARGE")
        files.append(
            {
                "path": f"{target_directory}/{document_type}/{identifier}.yaml",
                "content": normalized,
            }
        )
    if not files:
        raise PublicationInvalid("PUBLICATION_DOCUMENTS_REQUIRED")
    return files


def _pull_request_from_mapping(
    value: Mapping[str, Any], owner: str, repository: str
) -> tuple[int, str] | None:
    number = value.get("number")
    url = value.get("html_url") or value.get("url")
    prefix = f"https://github.com/{owner}/{repository}/pull/"
    if isinstance(number, int) and url == f"{prefix}{number}":
        return number, url
    return None


def _pull_request_from_text(
    value: str, owner: str, repository: str
) -> tuple[int, str] | None:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        match = re.search(
            rf"https://github\.com/{re.escape(owner)}/{re.escape(repository)}/pull/(\d+)",
            value,
        )
        return (int(match.group(1)), match.group(0)) if match else None
    return _safe_pull_request(parsed, owner, repository)


def _safe_pull_request(result: Any, owner: str, repository: str) -> tuple[int, str]:
    values: list[Any] = [result]
    while values:
        value = values.pop()
        if isinstance(value, Mapping):
            found = _pull_request_from_mapping(value, owner, repository)
            if found is not None:
                return found
            if not ({"number", "html_url", "url"} & value.keys()):
                values.extend(value.values())
        elif isinstance(value, (list, tuple)):
            values.extend(value)
        elif isinstance(value, str):
            found = _pull_request_from_text(value, owner, repository)
            if found is not None:
                return found
        elif hasattr(value, "text"):
            values.append(value.text)
    raise PublicationExternalError("PUBLICATION_PR_RESULT_INVALID")


def _validated_pull_request(
    result: Any,
    *,
    owner: str,
    repository: str,
    number: int,
    head: str,
    base: str,
) -> tuple[int, str]:
    expected_url = f"https://github.com/{owner}/{repository}/pull/{number}"
    values: list[Any] = [result]
    while values:
        value = values.pop()
        if isinstance(value, Mapping):
            candidate_number = value.get("number")
            candidate_url = value.get("html_url") or value.get("url")
            candidate_head = value.get("head")
            candidate_base = value.get("base")
            head_ref = (
                candidate_head.get("ref")
                if isinstance(candidate_head, Mapping)
                else candidate_head
            )
            base_ref = (
                candidate_base.get("ref")
                if isinstance(candidate_base, Mapping)
                else candidate_base
            )
            if (
                candidate_number == number
                and candidate_url == expected_url
                and head_ref == head
                and base_ref == base
            ):
                return number, expected_url
            values.extend(value.values())
        elif isinstance(value, (list, tuple)):
            values.extend(value)
        elif isinstance(value, str):
            try:
                values.append(json.loads(value))
            except json.JSONDecodeError:
                continue
        elif hasattr(value, "text"):
            values.append(value.text)
    raise PublicationExternalError("PUBLICATION_PR_VERIFICATION_FAILED")


def _result_mappings(result: Any):
    values: list[Any] = [result]
    while values:
        value = values.pop()
        if isinstance(value, Mapping):
            yield value
            values.extend(value.values())
        elif isinstance(value, (list, tuple)):
            values.extend(value)
        elif isinstance(value, str):
            try:
                values.append(json.loads(value))
            except json.JSONDecodeError:
                continue
        elif hasattr(value, "text"):
            values.append(value.text)


def _github_merge_evidence(
    result: Any, *, owner: str, repository: str, number: int
) -> MergeEvidence:
    expected_url = f"https://github.com/{owner}/{repository}/pull/{number}"
    for value in _result_mappings(result):
        url = value.get("html_url") or value.get("url")
        if value.get("number") != number or url != expected_url:
            continue
        body = str(value.get("body") or "")
        match = re.search(r"Content-SHA256:\s*`([0-9a-f]{64})`", body)
        return MergeEvidence(
            merged=value.get("merged") is True,
            commit_id=str(value.get("merge_commit_sha") or ""),
            content_hash=match.group(1) if match else "",
        )
    raise PublicationExternalError("PUBLICATION_PR_VERIFICATION_FAILED")


class GitHubPublicationService:
    def __init__(
        self,
        *,
        changesets: ChangeSetService,
        decisions: DecisionService,
        repository: SQLitePublicationRepository,
        gateway: PublicationGateway,
        reconciler: Any | None = None,
    ) -> None:
        self._changesets = changesets
        self._decisions = decisions
        self._repository = repository
        self._gateway = gateway
        self._reconciler = reconciler

    def _assert_current(
        self,
        scope: ChangeSetScope,
        publication: StoredPublication,
        *,
        roles: set[str],
    ) -> Any:
        if "Approver" not in roles:
            raise PublicationConflict("PUBLICATION_APPROVER_REQUIRED")
        decision = self._decisions.assert_approved(scope, publication.changeset_id)
        changeset = self._changesets.get(scope, publication.changeset_id)
        if (
            changeset.state != "approved"
            or changeset.revision != publication.revision
            or changeset.content_hash != publication.content_hash
            or decision.revision != publication.revision
            or decision.content_hash != publication.content_hash
        ):
            raise PublicationConflict("PUBLICATION_CONTENT_STALE")
        return changeset

    @staticmethod
    def _arguments(
        publication: StoredPublication, files: list[dict[str, str]]
    ) -> tuple[str, dict[str, Any]]:
        common = {"owner": publication.owner, "repo": publication.repository}
        if publication.step == "search":
            return "search_pull_requests", {
                "query": (
                    f"repo:{publication.owner}/{publication.repository} "
                    f"is:pr head:{publication.branch}"
                )
            }
        if publication.step == "branch":
            return "create_branch", {
                **common,
                "branch": publication.branch,
                "from_branch": publication.base_branch,
            }
        if publication.step == "push":
            return "push_files", {
                **common,
                "branch": publication.branch,
                "files": files,
                "message": f"Publish approved ChangeSet {publication.changeset_id}",
            }
        if publication.step == "pull_request":
            return "create_pull_request", {
                **common,
                "title": f"Publish approved ChangeSet {publication.changeset_id[:8]}",
                "body": (
                    f"Revision {publication.revision}\n\n"
                    f"Content-SHA256: `{publication.content_hash}`"
                ),
                "head": publication.branch,
                "base": publication.base_branch,
            }
        if publication.step == "verify" and publication.pull_request_number > 0:
            return "pull_request_read", {
                **common,
                "pullNumber": publication.pull_request_number,
                "method": "get",
            }
        raise PublicationConflict("PUBLICATION_STEP_INVALID")

    async def _prepare(
        self,
        scope: ChangeSetScope,
        publication: StoredPublication,
        *,
        roles: set[str],
        replay: bool = False,
    ) -> PublicationOutcome:
        changeset = self._assert_current(scope, publication, roles=roles)
        files = _files(changeset.content, publication.target_directory)
        tool, arguments = self._arguments(publication, files)
        try:
            approval = await self._gateway.request_approval(tool, arguments)
        except PublicationConsentRequired:
            self._repository.fail(
                scope,
                publication.id,
                error_code="PUBLICATION_CONSENT_REQUIRED",
                now=datetime.now(UTC).isoformat(),
            )
            raise
        except Exception as exc:
            self._repository.fail(
                scope,
                publication.id,
                error_code="PUBLICATION_EXTERNAL_FAILURE",
                now=datetime.now(UTC).isoformat(),
            )
            raise PublicationExternalError("PUBLICATION_EXTERNAL_FAILURE") from exc
        awaiting = self._repository.await_approval(
            scope,
            publication.id,
            approval.id,
            now=datetime.now(UTC).isoformat(),
        )
        return PublicationOutcome(awaiting, approval, replay)

    async def publish(
        self,
        scope: ChangeSetScope,
        request: PublicationRequest,
        *,
        roles: set[str],
    ) -> PublicationOutcome:
        if "Approver" not in roles:
            raise PublicationConflict("PUBLICATION_APPROVER_REQUIRED")
        decision = self._decisions.assert_approved(scope, request.changeset_id)
        changeset = self._changesets.get(scope, request.changeset_id)
        if (
            changeset.state != "approved"
            or changeset.revision != request.revision
            or changeset.content_hash != request.content_hash
            or decision.revision != request.revision
            or decision.content_hash != request.content_hash
        ):
            raise PublicationConflict("PUBLICATION_CONTENT_STALE")

        _files(changeset.content, request.target_directory)
        branch = f"assured/{request.changeset_id[:8]}-{request.content_hash[:12]}"
        request_hash = sha256(rfc8785.dumps(request.to_dict())).hexdigest()
        now = datetime.now(UTC).isoformat()
        publication_id = str(uuid4())
        existing, replay = self._repository.reserve(
            scope,
            request,
            publication_id=publication_id,
            branch=branch,
            request_hash=request_hash,
            now=now,
        )
        if replay and existing is not None:
            return PublicationOutcome(existing, None, True)
        if existing is not None:
            publication_id = existing.id
        publication = self._repository.get(scope, publication_id)
        if publication is None:
            raise PublicationNotFound("PUBLICATION_NOT_FOUND")
        return await self._prepare(scope, publication, roles=roles)

    async def decide(
        self,
        scope: ChangeSetScope,
        publication_id: str,
        approval_id: str,
        *,
        approved: bool,
        roles: set[str],
    ) -> PublicationOutcome:
        publication = self.get(scope, publication_id)
        self._assert_current(scope, publication, roles=roles)
        if (
            publication.state != "awaiting_approval"
            or publication.approval_id != approval_id
        ):
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
            next_step = {
                "branch": "push",
                "push": "pull_request",
            }.get(publication.step)
            number = publication.pull_request_number
            url = publication.pull_request_url
            if publication.step == "search":
                try:
                    number, url = _safe_pull_request(
                        result, publication.owner, publication.repository
                    )
                    next_step = "verify"
                except PublicationExternalError:
                    next_step = "branch"
            elif publication.step == "pull_request":
                number, url = _safe_pull_request(
                    result, publication.owner, publication.repository
                )
                next_step = "verify"
            elif publication.step == "verify":
                number, url = _validated_pull_request(
                    result,
                    owner=publication.owner,
                    repository=publication.repository,
                    number=number,
                    head=publication.branch,
                    base=publication.base_branch,
                )
                completed = self._repository.complete(
                    scope,
                    publication.id,
                    pull_request_number=number,
                    pull_request_url=url,
                    now=datetime.now(UTC).isoformat(),
                )
                return PublicationOutcome(completed, None, False)
            if next_step is None:
                raise PublicationConflict("PUBLICATION_STEP_INVALID")
            advanced = self._repository.advance(
                scope,
                publication.id,
                approval_id,
                next_step=next_step,
                pull_request_number=number,
                pull_request_url=url,
                now=datetime.now(UTC).isoformat(),
            )
        except PublicationConsentRequired as exc:
            self._repository.fail(
                scope,
                publication.id,
                error_code=str(exc),
                now=datetime.now(UTC).isoformat(),
            )
            raise
        except PublicationExternalError as exc:
            now = datetime.now(UTC).isoformat()
            if approved and tool not in _READ_TOOLS:
                self._repository.require_intervention(
                    scope,
                    publication.id,
                    error_code="PUBLICATION_WRITE_OUTCOME_UNKNOWN",
                    now=now,
                )
            else:
                self._repository.fail(
                    scope, publication.id, error_code=str(exc), now=now
                )
            raise
        except Exception as exc:
            now = datetime.now(UTC).isoformat()
            if approved and tool not in _READ_TOOLS:
                self._repository.require_intervention(
                    scope,
                    publication.id,
                    error_code="PUBLICATION_WRITE_OUTCOME_UNKNOWN",
                    now=now,
                )
            else:
                self._repository.fail(
                    scope,
                    publication.id,
                    error_code="PUBLICATION_EXTERNAL_FAILURE",
                    now=now,
                )
            raise PublicationExternalError("PUBLICATION_EXTERNAL_FAILURE") from exc
        return await self._prepare(scope, advanced, roles=roles)

    def get(self, scope: ChangeSetScope, publication_id: str) -> StoredPublication:
        if not re.fullmatch(r"[0-9a-f-]{36}", publication_id):
            raise PublicationNotFound("PUBLICATION_NOT_FOUND")
        publication = self._repository.get(scope, publication_id)
        if publication is None:
            raise PublicationNotFound("PUBLICATION_NOT_FOUND")
        return publication

    async def reconcile(
        self, scope: ChangeSetScope, publication_id: str, *, roles: set[str],
        expected_etag: str,
    ) -> tuple[StoredPublication, tuple[Any, ...]]:
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
            "owner": publication.owner,
            "repo": publication.repository,
            "pullNumber": publication.pull_request_number,
            "method": "get",
        }
        result = await self._gateway.execute_read("pull_request_read", arguments)
        evidence = _github_merge_evidence(
            result,
            owner=publication.owner,
            repository=publication.repository,
            number=publication.pull_request_number,
        )
        try:
            reconciled = self._reconciler.reconcile(
                publication,
                evidence,
                scope=scope,
                operations=changeset.content["operations"],
            )
        except Exception as exc:
            if isinstance(exc, ReconciliationBlocked):
                raise PublicationConflict(str(exc)) from exc
            raise
        return self.get(scope, publication.id), reconciled.journal

    def journal(self, scope: ChangeSetScope, publication_id: str) -> tuple[Any, ...]:
        publication = self.get(scope, publication_id)
        if self._reconciler is None:
            return ()
        return self._reconciler.journal(scope, publication.id)

    def compensate(
        self, scope: ChangeSetScope, publication_id: str, *, roles: set[str],
        expected_etag: str,
    ) -> tuple[StoredPublication, tuple[Any, ...]]:
        publication = self.get(scope, publication_id)
        if "Admin" not in roles:
            raise PublicationConflict("PUBLICATION_ADMIN_REQUIRED")
        if publication.etag != expected_etag:
            raise PublicationConflict("PUBLICATION_REVISION_STALE")
        if self._reconciler is None:
            raise PublicationExternalError("PUBLICATION_RECONCILIATION_NOT_CONFIGURED")
        try:
            journal = self._reconciler.compensate(scope, publication)
        except Exception as exc:
            if isinstance(exc, ReconciliationBlocked):
                raise PublicationConflict(str(exc)) from exc
            raise
        return self.get(scope, publication.id), journal


_default_service: GitHubPublicationService | None = None


def default_publication_service() -> GitHubPublicationService:
    global _default_service
    if _default_service is None:
        from app.shared.settings import settings

        data_directory = Path(app.__file__).resolve().parent.parent / "data"
        database = data_directory / "authoring.sqlite3"
        repository = SQLitePublicationRepository(database)
        from app.modules.publication.internal.reconciliation import (
            OfficialFoundryMaterializer,
            ReconciliationService,
            SQLiteMaterializationJournal,
        )

        _default_service = GitHubPublicationService(
            changesets=default_changeset_service(),
            decisions=default_decision_service(),
            repository=repository,
            gateway=FoundryToolboxGateway(settings.publication_toolbox_endpoint),
            reconciler=ReconciliationService(
                OfficialFoundryMaterializer(),
                journal=SQLiteMaterializationJournal(database),
                publications=repository,
            ),
        )
    return _default_service
