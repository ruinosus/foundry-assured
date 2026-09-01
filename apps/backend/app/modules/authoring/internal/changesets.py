"""ChangeSets duráveis: regras no domínio, SQL parametrizado nos adapters."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol
from uuid import uuid4

import rfc8785

import app
from app.modules.okf.public import AuthoringInvalid, parse_authoring_document

_SOURCES = frozenset({"manual", "builder", "import", "migration"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|secret|token|api[_-]?key|connection[_-]?string)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(r"(?:bearer\s+\S+|AccountKey=|SharedAccessSignature=)", re.IGNORECASE)
_MAX_CONTENT_BYTES = 256 * 1024


class ChangeSetConflict(AuthoringInvalid):
    """A chave idempotente já representa outro comando."""


class ChangeSetNotFound(AuthoringInvalid):
    """O ChangeSet não existe no tenant e área consultados."""


class ChangeSetPreconditionFailed(AuthoringInvalid):
    """A revisão informada em If-Match não é mais a atual."""


@dataclass(frozen=True, slots=True)
class ChangeSetScope:
    tenant_id: str
    area_id: str
    actor_id: str

    def __post_init__(self) -> None:
        for field, value in (
            ("tenant_id", self.tenant_id),
            ("area_id", self.area_id),
            ("actor_id", self.actor_id),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise AuthoringInvalid(f"changeset.scope.{field}: identificador inválido")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(child) for child in value]
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        return "[REDACTED]"
    return value


def _canonical(value: Any) -> bytes:
    try:
        return rfc8785.dumps(value)
    except (TypeError, ValueError) as exc:
        raise AuthoringInvalid("changeset.content: deve ser JSON canônico") from exc


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class StoredChangeSet:
    id: str
    source: str
    state: str
    revision: int
    base_snapshot_id: str
    content: Mapping[str, Any]
    content_hash: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", _freeze(dict(self.content)))

    @property
    def etag(self) -> str:
        return f'"{self.revision}:{self.content_hash}"'

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "state": self.state,
            "revision": self.revision,
            "etag": self.etag,
            "base_snapshot_id": self.base_snapshot_id,
            "content": _thaw(self.content),
            "content_hash": self.content_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ChangeSetRepository(Protocol):
    def create(
        self,
        scope: ChangeSetScope,
        record: StoredChangeSet,
        *,
        key_hash: str,
        request_hash: str,
    ) -> tuple[StoredChangeSet, bool]: ...

    def get(self, scope: ChangeSetScope, changeset_id: str) -> StoredChangeSet | None: ...
    def get_revision(
        self, scope: ChangeSetScope, changeset_id: str, revision: int
    ) -> StoredChangeSet | None: ...
    def list(self, scope: ChangeSetScope) -> list[StoredChangeSet]: ...

    def append(
        self,
        scope: ChangeSetScope,
        record: StoredChangeSet,
        *,
        expected_revision: int,
        expected_content_hash: str,
    ) -> StoredChangeSet: ...
    def transition(
        self,
        scope: ChangeSetScope,
        record: StoredChangeSet,
        *,
        expected_state: str,
        expected_revision: int,
        expected_content_hash: str,
    ) -> StoredChangeSet: ...


class _SqlChangeSetRepository:
    def __init__(
        self,
        connection_factory: Callable[[], Any],
        *,
        placeholder: str,
        begin_statement: str,
    ) -> None:
        self._connection_factory = connection_factory
        self._placeholder = placeholder
        self._begin_statement = begin_statement
        self._initialize()

    def _sql(self, statement: str) -> str:
        return statement.replace("?", self._placeholder)

    def _initialize(self) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS authoring_changesets (
                tenant_id TEXT NOT NULL, area_id TEXT NOT NULL, changeset_id TEXT NOT NULL,
                source TEXT NOT NULL, state TEXT NOT NULL, current_revision BIGINT NOT NULL,
                created_by_oid TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, area_id, changeset_id)
            )""",
            """CREATE TABLE IF NOT EXISTS authoring_changeset_revisions (
                tenant_id TEXT NOT NULL, area_id TEXT NOT NULL, changeset_id TEXT NOT NULL,
                revision BIGINT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
                base_snapshot_id TEXT NOT NULL, content_json TEXT NOT NULL,
                content_hash TEXT NOT NULL, author_oid TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, area_id, changeset_id, revision)
            )""",
            """CREATE TABLE IF NOT EXISTS authoring_idempotency_keys (
                tenant_id TEXT NOT NULL, area_id TEXT NOT NULL, actor_oid TEXT NOT NULL,
                operation TEXT NOT NULL, key_hash TEXT NOT NULL, request_hash TEXT NOT NULL,
                resource_id TEXT NOT NULL, response_status BIGINT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, area_id, actor_oid, operation, key_hash)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_authoring_changesets_scope ON authoring_changesets (tenant_id, area_id, updated_at)",
        )
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            for statement in statements:
                cursor.execute(statement)
            connection.commit()
            try:
                cursor.execute("SELECT state FROM authoring_changeset_revisions WHERE 1 = 0")
            except Exception:  # noqa: BLE001 - adapters DB-API não compartilham exceção de schema
                connection.rollback()
                cursor.execute(
                    "ALTER TABLE authoring_changeset_revisions "
                    "ADD COLUMN state TEXT NOT NULL DEFAULT 'draft'"
                )
                connection.commit()
        finally:
            connection.close()

    def _begin(self, connection) -> Any:
        cursor = connection.cursor()
        cursor.execute(self._begin_statement)
        return cursor

    @staticmethod
    def _record(row) -> StoredChangeSet:
        return StoredChangeSet(
            id=row[0],
            source=row[1],
            state=row[2],
            revision=int(row[3]),
            base_snapshot_id=row[4],
            content=json.loads(row[5]),
            content_hash=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    def _select(self, cursor, scope: ChangeSetScope, changeset_id: str):
        return cursor.execute(
            self._sql(
                """SELECT c.changeset_id, c.source, c.state, c.current_revision,
                          r.base_snapshot_id, r.content_json, r.content_hash,
                          c.created_at, c.updated_at
                   FROM authoring_changesets c
                   JOIN authoring_changeset_revisions r
                     ON r.tenant_id = c.tenant_id AND r.area_id = c.area_id
                    AND r.changeset_id = c.changeset_id AND r.revision = c.current_revision
                   WHERE c.tenant_id = ? AND c.area_id = ? AND c.changeset_id = ?"""
            ),
            (scope.tenant_id, scope.area_id, changeset_id),
        ).fetchone()

    def create(
        self,
        scope: ChangeSetScope,
        record: StoredChangeSet,
        *,
        key_hash: str,
        request_hash: str,
    ) -> tuple[StoredChangeSet, bool]:
        connection = self._connection_factory()
        try:
            cursor = self._begin(connection)
            existing = cursor.execute(
                self._sql(
                    """SELECT request_hash, resource_id FROM authoring_idempotency_keys
                       WHERE tenant_id = ? AND area_id = ? AND actor_oid = ?
                         AND operation = ? AND key_hash = ?"""
                ),
                (scope.tenant_id, scope.area_id, scope.actor_id, "create", key_hash),
            ).fetchone()
            if existing is not None:
                if existing[0] != request_hash:
                    raise ChangeSetConflict("IDEMPOTENCY_KEY_REUSED")
                persisted = self._select(cursor, scope, existing[1])
                connection.commit()
                if persisted is None:
                    raise RuntimeError("idempotency resource is missing")
                return self._record(persisted), True

            cursor.execute(
                self._sql(
                    """INSERT INTO authoring_changesets
                       (tenant_id, area_id, changeset_id, source, state, current_revision,
                        created_by_oid, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    scope.tenant_id,
                    scope.area_id,
                    record.id,
                    record.source,
                    record.state,
                    record.revision,
                    scope.actor_id,
                    record.created_at,
                    record.updated_at,
                ),
            )
            self._insert_revision(cursor, scope, record)
            cursor.execute(
                self._sql(
                    """INSERT INTO authoring_idempotency_keys
                       (tenant_id, area_id, actor_oid, operation, key_hash, request_hash,
                        resource_id, response_status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    scope.tenant_id,
                    scope.area_id,
                    scope.actor_id,
                    "create",
                    key_hash,
                    request_hash,
                    record.id,
                    201,
                    record.created_at,
                ),
            )
            connection.commit()
            return record, False
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _insert_revision(self, cursor, scope: ChangeSetScope, record: StoredChangeSet) -> None:
        cursor.execute(
            self._sql(
                     """INSERT INTO authoring_changeset_revisions
                         (tenant_id, area_id, changeset_id, revision, state, base_snapshot_id,
                    content_json, content_hash, author_oid, created_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            ),
            (
                scope.tenant_id,
                scope.area_id,
                record.id,
                record.revision,
                record.state,
                record.base_snapshot_id,
                json.dumps(_thaw(record.content), sort_keys=True, separators=(",", ":")),
                record.content_hash,
                scope.actor_id,
                record.updated_at,
            ),
        )

    def get(self, scope: ChangeSetScope, changeset_id: str) -> StoredChangeSet | None:
        connection = self._connection_factory()
        try:
            row = self._select(connection.cursor(), scope, changeset_id)
            return self._record(row) if row is not None else None
        finally:
            connection.close()

    def get_revision(
        self, scope: ChangeSetScope, changeset_id: str, revision: int
    ) -> StoredChangeSet | None:
        connection = self._connection_factory()
        try:
            row = connection.cursor().execute(
                self._sql(
                    """SELECT c.changeset_id, c.source, r.state, r.revision,
                              r.base_snapshot_id, r.content_json, r.content_hash,
                              c.created_at, r.created_at
                       FROM authoring_changesets c
                       JOIN authoring_changeset_revisions r
                         ON r.tenant_id = c.tenant_id AND r.area_id = c.area_id
                        AND r.changeset_id = c.changeset_id
                       WHERE c.tenant_id = ? AND c.area_id = ? AND c.changeset_id = ?
                         AND r.revision = ?"""
                ),
                (scope.tenant_id, scope.area_id, changeset_id, revision),
            ).fetchone()
            return self._record(row) if row is not None else None
        finally:
            connection.close()

    def list(self, scope: ChangeSetScope) -> list[StoredChangeSet]:
        connection = self._connection_factory()
        try:
            rows = connection.cursor().execute(
                self._sql(
                    """SELECT c.changeset_id, c.source, c.state, c.current_revision,
                              r.base_snapshot_id, r.content_json, r.content_hash,
                              c.created_at, c.updated_at
                       FROM authoring_changesets c
                       JOIN authoring_changeset_revisions r
                         ON r.tenant_id = c.tenant_id AND r.area_id = c.area_id
                        AND r.changeset_id = c.changeset_id
                        AND r.revision = c.current_revision
                       WHERE c.tenant_id = ? AND c.area_id = ?
                       ORDER BY c.updated_at DESC, c.changeset_id"""
                ),
                (scope.tenant_id, scope.area_id),
            ).fetchall()
            return [self._record(row) for row in rows]
        finally:
            connection.close()

    def append(
        self,
        scope: ChangeSetScope,
        record: StoredChangeSet,
        *,
        expected_revision: int,
        expected_content_hash: str,
    ) -> StoredChangeSet:
        connection = self._connection_factory()
        try:
            cursor = self._begin(connection)
            changed = cursor.execute(
                self._sql(
                    """UPDATE authoring_changesets SET state = ?, current_revision = ?, updated_at = ?
                       WHERE tenant_id = ? AND area_id = ? AND changeset_id = ?
                         AND current_revision = ?
                         AND EXISTS (
                           SELECT 1 FROM authoring_changeset_revisions r
                           WHERE r.tenant_id = authoring_changesets.tenant_id
                             AND r.area_id = authoring_changesets.area_id
                             AND r.changeset_id = authoring_changesets.changeset_id
                             AND r.revision = authoring_changesets.current_revision
                             AND r.content_hash = ?
                         )"""
                ),
                (
                    record.state,
                    record.revision,
                    record.updated_at,
                    scope.tenant_id,
                    scope.area_id,
                    record.id,
                    expected_revision,
                    expected_content_hash,
                ),
            ).rowcount
            if changed != 1:
                raise ChangeSetPreconditionFailed("CHANGESET_REVISION_STALE")
            self._insert_revision(cursor, scope, record)
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def transition(
        self,
        scope: ChangeSetScope,
        record: StoredChangeSet,
        *,
        expected_state: str,
        expected_revision: int,
        expected_content_hash: str,
    ) -> StoredChangeSet:
        connection = self._connection_factory()
        try:
            cursor = self._begin(connection)
            changed = cursor.execute(
                self._sql(
                    """UPDATE authoring_changesets SET state = ?, updated_at = ?
                       WHERE tenant_id = ? AND area_id = ? AND changeset_id = ?
                         AND state = ? AND current_revision = ?
                         AND EXISTS (
                           SELECT 1 FROM authoring_changeset_revisions r
                           WHERE r.tenant_id = authoring_changesets.tenant_id
                             AND r.area_id = authoring_changesets.area_id
                             AND r.changeset_id = authoring_changesets.changeset_id
                             AND r.revision = authoring_changesets.current_revision
                             AND r.content_hash = ?
                         )"""
                ),
                (
                    record.state,
                    record.updated_at,
                    scope.tenant_id,
                    scope.area_id,
                    record.id,
                    expected_state,
                    expected_revision,
                    expected_content_hash,
                ),
            ).rowcount
            if changed != 1:
                raise ChangeSetPreconditionFailed("CHANGESET_REVISION_STALE")
            cursor.execute(
                self._sql(
                    """UPDATE authoring_changeset_revisions SET state = ?
                       WHERE tenant_id = ? AND area_id = ? AND changeset_id = ?
                         AND revision = ? AND content_hash = ?"""
                ),
                (
                    record.state,
                    scope.tenant_id,
                    scope.area_id,
                    record.id,
                    record.revision,
                    record.content_hash,
                ),
            )
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class SQLiteChangeSetRepository(_SqlChangeSetRepository):
    def __init__(self, path: str | Path) -> None:
        database = Path(path)
        database.parent.mkdir(parents=True, exist_ok=True)

        def connect():
            return sqlite3.connect(database, timeout=5)

        super().__init__(connect, placeholder="?", begin_statement="BEGIN IMMEDIATE")


class PostgresChangeSetRepository(_SqlChangeSetRepository):
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        super().__init__(connection_factory, placeholder="%s", begin_statement="BEGIN")


class ChangeSetService:
    def __init__(self, repository: ChangeSetRepository) -> None:
        self._repository = repository

    @staticmethod
    def _content(content: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        if not isinstance(content, Mapping):
            raise AuthoringInvalid("changeset.content: deve ser um objeto")
        redacted = _redact(content)
        operations = redacted.get("operations")
        if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
            raise AuthoringInvalid("changeset.content.operations: exige de 1 a 100 operações")
        for index, operation in enumerate(operations):
            if not isinstance(operation, Mapping):
                raise AuthoringInvalid(f"changeset.content.operations[{index}]: deve ser um objeto")
            if not _IDENTIFIER.fullmatch(str(operation.get("id", ""))):
                raise AuthoringInvalid(f"changeset.content.operations[{index}].id: identificador inválido")
            if operation.get("operation") not in {"create", "revise", "deprecate"}:
                raise AuthoringInvalid(f"changeset.content.operations[{index}].operation: valor desconhecido")
        canonical = _canonical(redacted)
        if len(canonical) > _MAX_CONTENT_BYTES:
            raise AuthoringInvalid("changeset.content: excede 256 KiB")
        return redacted, sha256(canonical).hexdigest()

    @staticmethod
    def _validate_documents(scope: ChangeSetScope, content: Mapping[str, Any]) -> None:
        for index, operation in enumerate(content["operations"]):
            raw_document = operation.get("document")
            if raw_document is None:
                continue
            if not isinstance(raw_document, str) or not raw_document.strip():
                raise AuthoringInvalid(
                    f"changeset.content.operations[{index}].document: deve ser texto OKF"
                )
            document = parse_authoring_document(
                raw_document,
                where=f"changeset.content.operations[{index}].document",
            )
            declared_type = operation.get("document_type")
            if declared_type is not None and declared_type != document.type:
                raise AuthoringInvalid(
                    f"changeset.content.operations[{index}].document_type: diverge do documento"
                )
            if document.tenant != scope.tenant_id or document.area != scope.area_id:
                raise AuthoringInvalid(
                    f"changeset.content.operations[{index}].document: escopo divergente"
                )

    @staticmethod
    def _identifier(value: str, *, field: str) -> str:
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise AuthoringInvalid(f"changeset.{field}: identificador inválido")
        return value

    def create(
        self,
        scope: ChangeSetScope,
        *,
        source: str,
        base_snapshot_id: str,
        content: Mapping[str, Any],
        idempotency_key: str,
    ) -> tuple[StoredChangeSet, bool]:
        if source not in _SOURCES:
            raise AuthoringInvalid("changeset.source: valor desconhecido")
        snapshot = self._identifier(base_snapshot_id, field="base_snapshot_id")
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
            raise AuthoringInvalid("changeset.idempotency_key: tamanho inválido")
        normalized, content_hash = self._content(content)
        self._validate_documents(scope, normalized)
        request_hash = sha256(
            _canonical({"source": source, "base_snapshot_id": snapshot, "content": normalized})
        ).hexdigest()
        now = _timestamp()
        record = StoredChangeSet(
            id=str(uuid4()),
            source=source,
            state="draft",
            revision=1,
            base_snapshot_id=snapshot,
            content=normalized,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
        )
        return self._repository.create(
            scope,
            record,
            key_hash=sha256(idempotency_key.encode()).hexdigest(),
            request_hash=request_hash,
        )

    def get(self, scope: ChangeSetScope, changeset_id: str) -> StoredChangeSet:
        identifier = self._identifier(changeset_id, field="id")
        record = self._repository.get(scope, identifier)
        if record is None:
            raise ChangeSetNotFound("CHANGESET_NOT_FOUND")
        return record

    def get_revision(
        self, scope: ChangeSetScope, changeset_id: str, revision: int
    ) -> StoredChangeSet:
        identifier = self._identifier(changeset_id, field="id")
        if not isinstance(revision, int) or revision < 1:
            raise AuthoringInvalid("changeset.revision: valor inválido")
        record = self._repository.get_revision(scope, identifier, revision)
        if record is None:
            raise ChangeSetNotFound("CHANGESET_REVISION_NOT_FOUND")
        return record

    def list(self, scope: ChangeSetScope) -> list[StoredChangeSet]:
        return self._repository.list(scope)

    def update(
        self,
        scope: ChangeSetScope,
        changeset_id: str,
        *,
        expected_etag: str,
        content: Mapping[str, Any],
        base_snapshot_id: str | None = None,
    ) -> StoredChangeSet:
        current = self.get(scope, changeset_id)
        if expected_etag != current.etag:
            raise ChangeSetPreconditionFailed("CHANGESET_REVISION_STALE")
        if current.state != "draft":
            raise ChangeSetPreconditionFailed("CHANGESET_SUBMITTED_IMMUTABLE")
        normalized, content_hash = self._content(content)
        self._validate_documents(scope, normalized)
        snapshot = (
            self._identifier(base_snapshot_id, field="base_snapshot_id")
            if base_snapshot_id is not None
            else current.base_snapshot_id
        )
        revised = StoredChangeSet(
            id=current.id,
            source=current.source,
            state="draft",
            revision=current.revision + 1,
            base_snapshot_id=snapshot,
            content=normalized,
            content_hash=content_hash,
            created_at=current.created_at,
            updated_at=_timestamp(),
        )
        return self._repository.append(
            scope,
            revised,
            expected_revision=current.revision,
            expected_content_hash=current.content_hash,
        )

    def submit(
        self, scope: ChangeSetScope, changeset_id: str, *, expected_etag: str
    ) -> StoredChangeSet:
        current = self.get(scope, changeset_id)
        if expected_etag != current.etag or current.state != "draft":
            raise ChangeSetPreconditionFailed("CHANGESET_REVISION_STALE")
        submitted = replace(current, state="submitted", updated_at=_timestamp())
        return self._repository.transition(
            scope,
            submitted,
            expected_state="draft",
            expected_revision=current.revision,
            expected_content_hash=current.content_hash,
        )

    def revise(
        self, scope: ChangeSetScope, changeset_id: str, *, expected_etag: str
    ) -> StoredChangeSet:
        current = self.get(scope, changeset_id)
        if expected_etag != current.etag or current.state != "submitted":
            raise ChangeSetPreconditionFailed("CHANGESET_REVISION_STALE")
        revised = replace(
            current,
            state="draft",
            revision=current.revision + 1,
            updated_at=_timestamp(),
        )
        return self._repository.append(
            scope,
            revised,
            expected_revision=current.revision,
            expected_content_hash=current.content_hash,
        )


_default_service: ChangeSetService | None = None


def default_changeset_service() -> ChangeSetService:
    global _default_service
    if _default_service is None:
        data_directory = Path(app.__file__).resolve().parent.parent / "data"
        database = data_directory / "authoring.sqlite3"
        _default_service = ChangeSetService(SQLiteChangeSetRepository(database))
    return _default_service
