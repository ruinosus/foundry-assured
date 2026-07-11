# HTML Artifacts (MVP) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a governed "HTML Artifacts" feature — generate AI HTML reports/presentations, store them immutably in Blob, list/preview them in a sandboxed viewer, gated by Entra App Roles with an approve-to-publish lifecycle.

**Architecture:** Metadata lives in a swappable `ArtifactStore` (InMemory/Table, mirroring `TenantStore`); immutable HTML content lives in Blob (`ArtifactContentStore`, InMemory/Blob). A thin `/artifacts` FastAPI router delegates to `app/services/artifacts.py`. Generation reuses the `answer_direct` LLM pattern (`AIProjectClient.aio` → `responses.create`). The frontend is a **bespoke page** (`/artifacts`, like `/tickets`) — **not** the domain registry — and renders content via an `<iframe srcdoc>` with `sandbox="allow-scripts"` (opaque origin, no `allow-same-origin`), which sidesteps the bearer-token-in-iframe problem: the HTML is fetched with `authedFetch` and injected as `srcdoc`.

**Tech Stack:** Python 3.12 · FastAPI · `pydantic-settings` · `azure-data-tables` (already a dep) · `azure-storage-blob` (already a dep) · `azure-ai-projects` (Responses API) · `DefaultAzureCredential` · Next.js 15 (App Router) · React 19 · MSAL bearer auth · Bicep/`azd`.

**Security posture (enterprise-accepted, locked decisions):**
- **Sandbox is the PRIMARY isolation boundary** (`srcdoc` + `sandbox="allow-scripts"` WITHOUT `allow-same-origin` → opaque origin, no access to app cookies/`sessionStorage`/DOM). Validation is defense-in-depth, **not** the primary control. We deliberately do **not** strip `<script>` (the sandbox contains it).
- **No anonymous storage** — Blob `allowBlobPublicAccess: false` (already set); all access mediated by the backend.
- **Managed identity only** — `DefaultAzureCredential`, zero keys.
- **RBAC by Entra App Role** — Author creates/edits, Approver/Admin publishes, Reader views (reuse `require_role`).
- **Immutability + integrity** — on publish, content is frozen and a SHA-256 hash is recorded; published versions are never mutated.
- **Tenant isolation enforced in the backend**, never trusting the path alone — every read/write validates the caller's tenant (`current_tenant_id()`, fallback `"default"` in `self_hosted`) against the record's `tenant_id`.
- **Infra-as-code** — the Blob container and Table are provisioned in Bicep.

**Out of scope (future phases, do NOT build now):** signed one-time render URLs, separate rendering origin/subdomain, external assets (`assets/` referenced by path — MVP requires self-contained HTML), PDF/zip export, an iterative chat-generator domain, diff/version-compare UI, Teams/SharePoint distribution.

---

## Locked decisions (from strategy critique, 2026-07-06)

1. **Viewer:** `<iframe srcdoc>` + `sandbox="allow-scripts"` for **self-contained HTML only**. Rejected: authenticated `<iframe src>` (bearer can't ride an iframe navigation; app has no cookie).
2. **Metadata:** Azure Table via `ArtifactStore` Protocol (auditable, queryable). Rejected: `manifest.json` in Blob (race conditions, unqueryable).
3. **Generation:** direct endpoint `POST /artifacts/html/generate` (governable, auditable, HITL-gated). Rejected for MVP: open chat-generator domain (prompt-injection surface).

---

## File Structure

**Backend** (all under `apps/backend/`):
- Create `app/artifacts/__init__.py` — package marker.
- Create `app/artifacts/models.py` — `ArtifactRecord` frozen dataclass, `ArtifactStatus` values, `ArtifactType` values, `new_artifact_id()`, `sha256_hex()`.
- Create `app/artifacts/store.py` — `ArtifactStore` Protocol + `InMemoryArtifactStore` + `TableArtifactStore`; `ArtifactContentStore` Protocol + `InMemoryContentStore` + `BlobContentStore`; entity (de)serialization helpers.
- Create `app/artifacts/factory.py` — `make_artifact_store()` / `make_content_store()` boot factories (mirror `_make_tenant_store`).
- Create `app/artifacts/validate.py` — `validate_html()` defense-in-depth checks (size cap, must-look-like-HTML). Does NOT strip scripts.
- Create `app/services/artifacts.py` — service layer: generate, create draft, list, get, get_content, request_approval, approve/publish, reject, archive; tenant-isolation enforcement; lifecycle rules.
- Create `app/api/artifacts.py` — thin router `/artifacts/html/*` with per-route `require_role` gates.
- Modify `app/api/__init__.py:6` (import) and register the router.
- Modify `app/core/settings.py` — add `artifact_*` fields.
- Modify `app/core/tenant.py` OR add a helper — `artifact_tenant_id()` returning `current_tenant_id() or "default"`.
- Create `eval/artifact_store_test.py`, `eval/artifact_service_test.py`, `eval/artifact_rbac_test.py` — `main() -> int` runner style.
- Modify `.github/workflows/ci.yml` — wire the new `*_test.py` modules.

**Infra** (under `infra/`):
- Modify `infra/resources.bicep` — add an `artifacts` blob container + an `artifacts` table on the existing storage account; grant the backend UAMI `Storage Blob Data Contributor` + `Storage Table Data Contributor`; output the account URL.
- Modify `infra/containerapps.bicep` — pass artifact env vars into the backend container app.

**Frontend** (all under `apps/frontend/`):
- Create `app/artifacts/page.tsx` — bespoke page wrapping `<ArtifactsView>` in `<AppShell>`.
- Create `app/artifacts/[id]/page.tsx` — detail/preview page.
- Create `components/artifacts/ArtifactsView.tsx` — list + "new" form (client component).
- Create `components/artifacts/ArtifactDetail.tsx` — metadata + lifecycle actions + `<SandboxViewer>`.
- Create `components/artifacts/SandboxViewer.tsx` — the `srcdoc` sandbox iframe.
- Create `app/api/artifacts/route.ts` — GET (list) + POST (generate) proxy.
- Create `app/api/artifacts/[...path]/route.ts` — catch-all proxy for `GET/POST` on `/artifacts/html/{id}[/content|/approve|/publish|/reject|/archive]`.
- Modify `components/shell/AppShell.tsx` — add `WORKSPACE_NAV` + `TITLES` entries.

---

## Data model (reference for all tasks)

`ArtifactRecord` (frozen dataclass):

| field | type | notes |
|---|---|---|
| `id` | `str` | `art_<12 hex>` |
| `tenant_id` | `str` | resolved tenant tid, or `"default"` in self_hosted |
| `title` | `str` | |
| `description` | `str` | |
| `type` | `str` | `presentation` \| `report` \| `walkthrough` |
| `status` | `str` | `draft` \| `pending_approval` \| `published` \| `rejected` \| `archived` |
| `created_by` | `str` | caller oid/upn |
| `created_at` | `str` | ISO 8601 (passed in — no `Date.now()` in generators; use `datetime.now(UTC)` in the service, which is allowed in normal request code) |
| `updated_at` | `str` | ISO 8601 |
| `approved_by` | `str \| None` | |
| `approved_at` | `str \| None` | |
| `version` | `int` | starts at 1 |
| `blob_path` | `str` | `{tenant_id}/{id}/v{version}/index.html` |
| `content_hash` | `str \| None` | SHA-256 hex, set on publish |

Table mapping: `PartitionKey=tenant_id`, `RowKey=id` (multiple artifacts per tenant partition). Scalar fields stored flat; none need JSON nesting (unlike `TenantRecord`).

Lifecycle transitions (enforced in the service):
- `draft → pending_approval` (author requests approval)
- `pending_approval → published` (Approver/Admin approves — freezes content, sets hash + approved_by/at)
- `pending_approval → rejected` (Approver/Admin rejects → back to author, editable again as draft)
- `published → archived` (Author/Admin)
- Content is mutable only while `draft`; on publish it is frozen.

---

## Chunk 1: Backend — models + ArtifactStore + ContentStore

### Task 1: Artifact data model

**Files:**
- Create: `apps/backend/app/artifacts/__init__.py`
- Create: `apps/backend/app/artifacts/models.py`
- Test: `apps/backend/eval/artifact_store_test.py`

- [ ] **Step 1: Write the failing test** (`eval/artifact_store_test.py`)

```python
"""Artifact model + store tests.

Run (from apps/backend/):  uv run python -m eval.artifact_store_test
"""
import sys

from app.artifacts.models import (
    ArtifactRecord,
    ArtifactStatus,
    new_artifact_id,
    sha256_hex,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    aid = new_artifact_id()
    check("id has art_ prefix", aid.startswith("art_"))
    check("id is unique", new_artifact_id() != new_artifact_id())
    check("sha256 known vector", sha256_hex("abc") ==
          "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    rec = ArtifactRecord(
        id=aid, tenant_id="default", title="T", description="D", type="report",
        status=ArtifactStatus.DRAFT, created_by="u1", created_at="2026-07-06T00:00:00Z",
        updated_at="2026-07-06T00:00:00Z", version=1,
        blob_path=f"default/{aid}/v1/index.html",
    )
    check("record is frozen", _is_frozen(rec))
    check("blob_path default fallback", rec.blob_path.startswith("default/"))

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


def _is_frozen(rec) -> bool:
    try:
        rec.title = "x"  # type: ignore[misc]
        return False
    except Exception:
        return True


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.artifacts'`.

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/app/artifacts/__init__.py` (empty).

Create `apps/backend/app/artifacts/models.py`:

```python
"""Artifact domain model — immutable metadata records."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass


class ArtifactStatus:
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ArtifactType:
    PRESENTATION = "presentation"
    REPORT = "report"
    WALKTHROUGH = "walkthrough"


ALLOWED_TYPES = frozenset(
    {ArtifactType.PRESENTATION, ArtifactType.REPORT, ArtifactType.WALKTHROUGH}
)


def new_artifact_id() -> str:
    return f"art_{secrets.token_hex(6)}"


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    tenant_id: str
    title: str
    description: str
    type: str
    status: str
    created_by: str
    created_at: str
    updated_at: str
    blob_path: str
    version: int = 1
    approved_by: str | None = None
    approved_at: str | None = None
    content_hash: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/artifacts/__init__.py apps/backend/app/artifacts/models.py apps/backend/eval/artifact_store_test.py
git commit -m "feat(artifacts): ArtifactRecord model + id/hash helpers"
```

---

### Task 2: `ArtifactStore` (metadata) — Protocol + InMemory + Table

**Files:**
- Create: `apps/backend/app/artifacts/store.py`
- Test: `apps/backend/eval/artifact_store_test.py` (extend)

- [ ] **Step 1: Extend the failing test** — add to `main()` after the model checks:

```python
    from app.artifacts.store import InMemoryArtifactStore

    store = InMemoryArtifactStore()
    check("get on empty is None", store.get("default", "nope") is None)
    store.put(rec)
    got = store.get("default", aid)
    check("put then get round-trips", got is not None and got.id == aid)
    check("list scoped to tenant", [r.id for r in store.list("default")] == [aid])
    check("list other tenant empty", store.list("other") == [])
    # tenant isolation: a get with the wrong tenant must not return the record
    check("get is tenant-scoped", store.get("other", aid) is None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: FAIL — `ImportError: cannot import name 'InMemoryArtifactStore'`.

- [ ] **Step 3: Implement `store.py`** (metadata stores only; content store added in Task 3):

```python
"""Artifact stores — metadata (Table) + content (Blob), each with an in-memory fake.

Mirrors app/core/tenant_store.py: a Protocol + InMemory fake for dev/CI + an
Azure impl that lazily imports the SDK at construction time.
"""
from __future__ import annotations

from typing import Protocol

from app.artifacts.models import ArtifactRecord


class ArtifactStore(Protocol):
    def get(self, tenant_id: str, artifact_id: str) -> ArtifactRecord | None: ...
    def put(self, rec: ArtifactRecord) -> None: ...
    def list(self, tenant_id: str) -> list[ArtifactRecord]: ...


class InMemoryArtifactStore:
    """Test/dev fake."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], ArtifactRecord] = {}

    def get(self, tenant_id: str, artifact_id: str) -> ArtifactRecord | None:
        return self._by_key.get((tenant_id, artifact_id))

    def put(self, rec: ArtifactRecord) -> None:
        self._by_key[(rec.tenant_id, rec.id)] = rec

    def list(self, tenant_id: str) -> list[ArtifactRecord]:
        return [r for (t, _), r in self._by_key.items() if t == tenant_id]


_FIELDS = (
    "title", "description", "type", "status", "created_by", "created_at",
    "updated_at", "blob_path", "version", "approved_by", "approved_at",
    "content_hash",
)


def _record_from_entity(e) -> ArtifactRecord:
    return ArtifactRecord(
        id=e["RowKey"],
        tenant_id=e["PartitionKey"],
        title=e.get("title", ""),
        description=e.get("description", ""),
        type=e.get("type", ""),
        status=e.get("status", ""),
        created_by=e.get("created_by", ""),
        created_at=e.get("created_at", ""),
        updated_at=e.get("updated_at", ""),
        blob_path=e.get("blob_path", ""),
        version=int(e.get("version", 1)),
        approved_by=e.get("approved_by") or None,
        approved_at=e.get("approved_at") or None,
        content_hash=e.get("content_hash") or None,
    )


class TableArtifactStore:
    """Azure Table Storage (keyless). PartitionKey=tenant_id, RowKey=artifact_id."""

    def __init__(self, account_url: str, table_name: str, credential) -> None:
        from azure.data.tables import TableServiceClient  # lazy, construction-time

        svc = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = svc.create_table_if_not_exists(table_name)

    def get(self, tenant_id: str, artifact_id: str) -> ArtifactRecord | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            e = self._table.get_entity(partition_key=tenant_id, row_key=artifact_id)
        except ResourceNotFoundError:
            return None
        return _record_from_entity(e)

    def put(self, rec: ArtifactRecord) -> None:
        entity = {"PartitionKey": rec.tenant_id, "RowKey": rec.id}
        for f in _FIELDS:
            val = getattr(rec, f)
            entity[f] = "" if val is None else val
        self._table.upsert_entity(entity)

    def list(self, tenant_id: str) -> list[ArtifactRecord]:
        rows = self._table.query_entities(
            "PartitionKey eq @t", parameters={"t": tenant_id}
        )
        return [_record_from_entity(e) for e in rows]
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/artifacts/store.py apps/backend/eval/artifact_store_test.py
git commit -m "feat(artifacts): ArtifactStore Protocol + InMemory + Table"
```

---

### Task 3: `ArtifactContentStore` (Blob) — Protocol + InMemory + Blob

**Files:**
- Modify: `apps/backend/app/artifacts/store.py`
- Test: `apps/backend/eval/artifact_store_test.py` (extend)

- [ ] **Step 1: Extend the test** — add after the metadata-store checks:

```python
    from app.artifacts.store import InMemoryContentStore

    content = InMemoryContentStore()
    path = f"default/{aid}/v1/index.html"
    content.put(path, "<html>hi</html>")
    check("content round-trips", content.get(path) == "<html>hi</html>")
    check("missing content is None", content.get("nope") is None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: FAIL — `ImportError: cannot import name 'InMemoryContentStore'`.

- [ ] **Step 3: Append to `store.py`:**

```python
class ArtifactContentStore(Protocol):
    def put(self, path: str, html: str) -> None: ...
    def get(self, path: str) -> str | None: ...


class InMemoryContentStore:
    """Test/dev fake."""

    def __init__(self) -> None:
        self._blobs: dict[str, str] = {}

    def put(self, path: str, html: str) -> None:
        self._blobs[path] = html

    def get(self, path: str) -> str | None:
        return self._blobs.get(path)


class BlobContentStore:
    """Azure Blob. One blob per artifact version at {tenant}/{id}/v{n}/index.html."""

    def __init__(self, account_url: str, container: str, credential) -> None:
        from azure.storage.blob import BlobServiceClient  # lazy, construction-time

        svc = BlobServiceClient(account_url=account_url, credential=credential)
        self._container = svc.get_container_client(container)
        try:
            self._container.create_container()
        except Exception:
            pass  # already exists

    def put(self, path: str, html: str) -> None:
        self._container.upload_blob(
            name=path, data=html.encode("utf-8"), overwrite=True,
            content_type="text/html",
        )

    def get(self, path: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            blob = self._container.download_blob(path)
        except ResourceNotFoundError:
            return None
        return blob.readall().decode("utf-8")
```

> Note: `content_type="text/html"` is set as blob metadata for correctness, but content is **never** served directly from Blob to the browser — always via the backend/proxy. `overwrite=True` is safe because the service only writes content while `status == draft`; published paths are frozen by lifecycle rules (Task 7), not by the blob layer.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/artifacts/store.py apps/backend/eval/artifact_store_test.py
git commit -m "feat(artifacts): ArtifactContentStore Protocol + InMemory + Blob"
```

---

## Chunk 2: Backend — settings, factory, tenant helper, validation

### Task 4: Settings + boot factory

**Files:**
- Modify: `apps/backend/app/core/settings.py`
- Create: `apps/backend/app/artifacts/factory.py`
- Test: `apps/backend/eval/artifact_store_test.py` (extend)

- [ ] **Step 1: Extend the test** — factory returns in-memory fakes when backend is `memory`:

```python
    import app.core.settings as settings_mod
    from app.artifacts import factory

    settings_mod.settings.artifact_store_backend = "memory"
    ms = factory.make_artifact_store()
    cs = factory.make_content_store()
    check("factory metadata=memory", type(ms).__name__ == "InMemoryArtifactStore")
    check("factory content=memory", type(cs).__name__ == "InMemoryContentStore")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: FAIL — `AttributeError: 'PlatformSettings' object has no attribute 'artifact_store_backend'` (and no `factory`).

- [ ] **Step 3a: Add settings fields** to `PlatformSettings` in `apps/backend/app/core/settings.py` (near the `tenant_store_*` fields):

```python
    # Artifacts (HTML artifacts feature)
    artifact_store_backend: str = "table"       # "table" | "memory"
    artifact_store_account_url: str = ""         # ARTIFACT_STORE_ACCOUNT_URL
    artifact_table: str = "artifacts"            # ARTIFACT_TABLE
    artifact_blob_account_url: str = ""          # ARTIFACT_BLOB_ACCOUNT_URL
    artifact_container: str = "artifacts"        # ARTIFACT_CONTAINER
    artifact_max_html_bytes: int = 2_000_000     # 2 MB cap (defense-in-depth)
```

- [ ] **Step 3b: Create `apps/backend/app/artifacts/factory.py`:**

```python
"""Boot factories for artifact stores — mirror app.core.auth._make_tenant_store."""
from __future__ import annotations

from app.core.settings import settings


def make_artifact_store():
    if settings.artifact_store_backend == "memory":
        from app.artifacts.store import InMemoryArtifactStore

        return InMemoryArtifactStore()
    from azure.identity import DefaultAzureCredential

    from app.artifacts.store import TableArtifactStore

    if not settings.artifact_store_account_url:
        raise RuntimeError(
            "artifact_store_backend=table requires ARTIFACT_STORE_ACCOUNT_URL"
        )
    return TableArtifactStore(
        settings.artifact_store_account_url,
        settings.artifact_table,
        DefaultAzureCredential(),
    )


def make_content_store():
    if settings.artifact_store_backend == "memory":
        from app.artifacts.store import InMemoryContentStore

        return InMemoryContentStore()
    from azure.identity import DefaultAzureCredential

    from app.artifacts.store import BlobContentStore

    if not settings.artifact_blob_account_url:
        raise RuntimeError(
            "artifact_store_backend=table requires ARTIFACT_BLOB_ACCOUNT_URL"
        )
    return BlobContentStore(
        settings.artifact_blob_account_url,
        settings.artifact_container,
        DefaultAzureCredential(),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_store_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/core/settings.py apps/backend/app/artifacts/factory.py apps/backend/eval/artifact_store_test.py
git commit -m "feat(artifacts): settings fields + store boot factories"
```

---

### Task 5: HTML validation (defense-in-depth) + tenant helper

**Files:**
- Create: `apps/backend/app/artifacts/validate.py`
- Modify: `apps/backend/app/core/tenant.py` (add `artifact_tenant_id()`)
- Test: `apps/backend/eval/artifact_service_test.py` (new)

- [ ] **Step 1: Write the failing test** (`eval/artifact_service_test.py`):

```python
"""Artifact validation + tenant-scope tests.

Run (from apps/backend/):  uv run python -m eval.artifact_service_test
"""
import sys

from app.artifacts.validate import ValidationError, validate_html


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # valid HTML passes and is returned unchanged (we do NOT strip scripts —
    # the iframe sandbox is the boundary)
    html = "<!doctype html><html><body><script>1</script></body></html>"
    check("valid html passes unchanged", validate_html(html, max_bytes=1000) == html)

    # oversize is rejected
    check("oversize rejected", _raises(lambda: validate_html("x" * 50, max_bytes=10)))

    # non-HTML blob rejected
    check("non-html rejected", _raises(lambda: validate_html("just text", max_bytes=1000)))

    # empty rejected
    check("empty rejected", _raises(lambda: validate_html("", max_bytes=1000)))

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except ValidationError:
        return True


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.artifacts.validate'`.

- [ ] **Step 3a: Create `apps/backend/app/artifacts/validate.py`:**

```python
"""Defense-in-depth HTML validation.

The PRIMARY isolation boundary is the frontend iframe sandbox (opaque origin,
no allow-same-origin). This validation is a secondary gate: it enforces a size
cap and a minimal "looks like HTML" shape. It deliberately does NOT strip
<script> — the sandbox contains it, and stripping would break legitimate
AI-generated interactive artifacts.
"""
from __future__ import annotations

import re

_HTML_HINT = re.compile(r"<\s*(!doctype\s+html|html|body|div|section)\b", re.IGNORECASE)


class ValidationError(ValueError):
    pass


def validate_html(html: str, *, max_bytes: int) -> str:
    if not html or not html.strip():
        raise ValidationError("empty artifact")
    if len(html.encode("utf-8")) > max_bytes:
        raise ValidationError(f"artifact exceeds {max_bytes} bytes")
    if not _HTML_HINT.search(html):
        raise ValidationError("content does not look like HTML")
    return html
```

- [ ] **Step 3b: Add `artifact_tenant_id()` to `apps/backend/app/core/tenant.py`** (next to `current_tenant_id`):

```python
def artifact_tenant_id() -> str:
    """Tenant partition for artifacts. In shared mode this is the resolved tid;
    in self_hosted/dedicated there is no per-request tenant, so use 'default'."""
    return current_tenant_id() or "default"
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/artifacts/validate.py apps/backend/app/core/tenant.py apps/backend/eval/artifact_service_test.py
git commit -m "feat(artifacts): HTML validation + artifact_tenant_id helper"
```

---

## Chunk 3: Backend — service layer (generate + lifecycle)

### Task 6: Service — create draft, list, get, get_content (with tenant isolation)

**Files:**
- Create: `apps/backend/app/services/artifacts.py`
- Test: `apps/backend/eval/artifact_service_test.py` (extend)

The service holds module-level store singletons (lazy, so tests can inject fakes), mirroring how other services resolve dependencies. It takes an explicit `user` argument (contextvar is unreliable in async paths — see `answer_direct`).

- [ ] **Step 1: Extend the test** — add a service-level section. Inject in-memory stores directly:

```python
    import app.services.artifacts as svc
    from app.artifacts.store import InMemoryArtifactStore, InMemoryContentStore

    svc._store = InMemoryArtifactStore()
    svc._content = InMemoryContentStore()

    class U:  # minimal user stub
        oid = "author-1"
        upn = "author@x"
        roles = ["Author"]

    rec = svc.create_draft(
        tenant_id="t1", title="Q3", description="d", type="report",
        html="<html><body>ok</body></html>", user=U(),
    )
    check("draft created", rec.status == "draft" and rec.created_by == "author-1")
    check("content stored", svc.get_content("t1", rec.id, user=U()) == "<html><body>ok</body></html>")
    check("listed for tenant", [r.id for r in svc.list_artifacts("t1")] == [rec.id])

    # tenant isolation: cannot read another tenant's artifact
    check("cross-tenant get denied", _raises_forbidden(lambda: svc.get_content("t2", rec.id, user=U())))

    # invalid type rejected
    check("bad type rejected", _raises_value(lambda: svc.create_draft(
        tenant_id="t1", title="x", description="", type="bogus",
        html="<html></html>", user=U())))
```

Add helpers `_raises_forbidden` / `_raises_value` mirroring `_raises` (catching `svc.Forbidden` / `ValueError`).

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.artifacts'`.

- [ ] **Step 3: Create `apps/backend/app/services/artifacts.py`** (create/list/get/get_content portion):

```python
"""Artifact service — generation + governed lifecycle.

Stores are module-level singletons resolved lazily via the factories so tests
can override `_store` / `_content` with in-memory fakes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.artifacts.factory import make_artifact_store, make_content_store
from app.artifacts.models import (
    ALLOWED_TYPES,
    ArtifactRecord,
    ArtifactStatus,
    new_artifact_id,
    sha256_hex,
)
from app.artifacts.validate import validate_html
from app.core.settings import settings

_store = None
_content = None


class Forbidden(Exception):
    """Caller may not act on this artifact (tenant or role mismatch)."""


def _stores():
    global _store, _content
    if _store is None:
        _store = make_artifact_store()
    if _content is None:
        _content = make_content_store()
    return _store, _content


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor(user) -> str:
    return getattr(user, "oid", None) or getattr(user, "upn", None) or "unknown"


def _load_scoped(tenant_id: str, artifact_id: str) -> ArtifactRecord:
    store, _ = _stores()
    rec = store.get(tenant_id, artifact_id)
    if rec is None or rec.tenant_id != tenant_id:
        # Never leak existence across tenants.
        raise Forbidden("artifact not found in tenant")
    return rec


def create_draft(*, tenant_id: str, title: str, description: str, type: str,
                 html: str, user) -> ArtifactRecord:
    if type not in ALLOWED_TYPES:
        raise ValueError(f"invalid artifact type: {type}")
    html = validate_html(html, max_bytes=settings.artifact_max_html_bytes)
    store, content = _stores()
    aid = new_artifact_id()
    now = _now()
    blob_path = f"{tenant_id}/{aid}/v1/index.html"
    rec = ArtifactRecord(
        id=aid, tenant_id=tenant_id, title=title, description=description,
        type=type, status=ArtifactStatus.DRAFT, created_by=_actor(user),
        created_at=now, updated_at=now, blob_path=blob_path, version=1,
    )
    content.put(blob_path, html)
    store.put(rec)
    return rec


def list_artifacts(tenant_id: str) -> list[ArtifactRecord]:
    store, _ = _stores()
    return store.list(tenant_id)


def get_artifact(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    return _load_scoped(tenant_id, artifact_id)


def get_content(tenant_id: str, artifact_id: str, *, user) -> str:
    rec = _load_scoped(tenant_id, artifact_id)
    _, content = _stores()
    html = content.get(rec.blob_path)
    if html is None:
        raise Forbidden("artifact content missing")
    return html
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/services/artifacts.py apps/backend/eval/artifact_service_test.py
git commit -m "feat(artifacts): service — create draft, list, get, get_content w/ tenant isolation"
```

---

### Task 7: Service — lifecycle (request approval, approve/publish, reject, archive)

**Files:**
- Modify: `apps/backend/app/services/artifacts.py`
- Test: `apps/backend/eval/artifact_service_test.py` (extend)

Publish freezes content and records `content_hash`. Reject returns to `draft`. Content edits allowed only in `draft`. Role is passed explicitly (the router enforces `require_role`, but the service re-checks approve/publish authority defense-in-depth via the passed `approver_roles`).

- [ ] **Step 1: Extend the test:**

```python
    # lifecycle
    r2 = svc.create_draft(tenant_id="t1", title="L", description="", type="report",
                          html="<html><body>v</body></html>", user=U())
    svc.request_approval("t1", r2.id, user=U())
    check("pending after request", svc.get_artifact("t1", r2.id, user=U()).status == "pending_approval")

    class A:  # approver
        oid = "appr-1"; upn = "a@x"; roles = ["Approver"]

    pub = svc.approve("t1", r2.id, user=A())
    check("published after approve", pub.status == "published")
    check("hash recorded", pub.content_hash == svc._hash_of("t1", r2.id))
    check("approved_by set", pub.approved_by == "appr-1")

    # cannot edit content once published (freeze)
    check("publish freezes content", _raises_value(
        lambda: svc.replace_content("t1", r2.id, "<html>new</html>", user=U())))

    # reject path
    r3 = svc.create_draft(tenant_id="t1", title="R", description="", type="report",
                          html="<html><body>x</body></html>", user=U())
    svc.request_approval("t1", r3.id, user=U())
    rej = svc.reject("t1", r3.id, user=A())
    check("rejected returns to draft", rej.status == "draft")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: FAIL — `AttributeError: module 'app.services.artifacts' has no attribute 'request_approval'`.

- [ ] **Step 3: Append lifecycle functions to `app/services/artifacts.py`:**

```python
from dataclasses import replace  # add to imports at top


def _save(rec: ArtifactRecord) -> ArtifactRecord:
    store, _ = _stores()
    store.put(rec)
    return rec


def _hash_of(tenant_id: str, artifact_id: str) -> str:
    rec = _load_scoped(tenant_id, artifact_id)
    _, content = _stores()
    return sha256_hex(content.get(rec.blob_path) or "")


def replace_content(tenant_id: str, artifact_id: str, html: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.DRAFT:
        raise ValueError("content editable only while draft")
    html = validate_html(html, max_bytes=settings.artifact_max_html_bytes)
    _, content = _stores()
    content.put(rec.blob_path, html)
    return _save(replace(rec, updated_at=_now()))


def request_approval(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.DRAFT:
        raise ValueError("only a draft can be submitted for approval")
    return _save(replace(rec, status=ArtifactStatus.PENDING_APPROVAL, updated_at=_now()))


def approve(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.PENDING_APPROVAL:
        raise ValueError("only a pending artifact can be approved")
    now = _now()
    return _save(replace(
        rec, status=ArtifactStatus.PUBLISHED, approved_by=_actor(user),
        approved_at=now, updated_at=now,
        content_hash=_hash_of(tenant_id, artifact_id),
    ))


def reject(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status != ArtifactStatus.PENDING_APPROVAL:
        raise ValueError("only a pending artifact can be rejected")
    return _save(replace(rec, status=ArtifactStatus.DRAFT, updated_at=_now()))


def archive(tenant_id: str, artifact_id: str, *, user) -> ArtifactRecord:
    rec = _load_scoped(tenant_id, artifact_id)
    if rec.status not in (ArtifactStatus.PUBLISHED, ArtifactStatus.DRAFT):
        raise ValueError("only draft/published artifacts can be archived")
    return _save(replace(rec, status=ArtifactStatus.ARCHIVED, updated_at=_now()))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/services/artifacts.py apps/backend/eval/artifact_service_test.py
git commit -m "feat(artifacts): governed lifecycle — request/approve/reject/archive + content freeze"
```

---

### Task 8: Service — LLM generation (answer_direct pattern)

**Files:**
- Modify: `apps/backend/app/services/artifacts.py`
- Test: `apps/backend/eval/artifact_service_test.py` (extend — patch the LLM boundary, never call Azure)

- [ ] **Step 1: Extend the test** — keep the test offline by reassigning the module-level `_generate_html` function to a fake (`generate()` resolves the global by name at call time, so this substitution takes effect). This is the same "patch the LLM boundary, never mock `DefaultAzureCredential`" principle used by the copilot service tests:

```python
    import asyncio

    async def fake_llm(prompt: str, artifact_type: str, user=None) -> str:
        return "<!doctype html><html><body><h1>gen</h1></body></html>"

    svc._generate_html = fake_llm  # patch the LLM boundary

    out = asyncio.run(svc.generate(
        tenant_id="t1", title="G", description="", type="report",
        prompt="make a report", user=U()))
    check("generate creates draft", out.status == "draft")
    check("generated content stored",
          "gen" in svc.get_content("t1", out.id, user=U()))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: FAIL — `AttributeError: module 'app.services.artifacts' has no attribute 'generate'`.

- [ ] **Step 3: Append generation to `app/services/artifacts.py`** (copy the `_responses` skeleton from `app/services/copilot.py:60-94`; verify the SDK surface against Foundry docs per CLAUDE.md rule #1):

```python
import contextlib  # add to imports
import inspect  # add to imports

_HTML_SYSTEM = (
    "You are an expert front-end engineer. Produce a SINGLE self-contained, "
    "responsive HTML document (all CSS and JS inline, no external requests, no "
    "external assets). Return ONLY the HTML, starting with <!doctype html>. "
    "The document must be safe to render inside a sandboxed iframe."
)


async def _generate_html(prompt: str, artifact_type: str, user=None) -> str:
    """LLM boundary — patched in tests. Mirrors app/services/copilot._responses."""
    from azure.ai.projects.aio import AIProjectClient

    from app.core.tenant import tenant_config
    from app.services.grounded import _async_credential

    cfg = tenant_config()
    credential = _async_credential(user)
    proj = AIProjectClient(
        endpoint=cfg.foundry_project_endpoint, credential=credential,
        allow_preview=True,
    )
    try:
        client = proj.get_openai_client()
        client = await client if inspect.isawaitable(client) else client
        instructions = f"{_HTML_SYSTEM}\nArtifact type: {artifact_type}."
        resp = await client.responses.create(
            model=cfg.foundry_model, instructions=instructions,
            input=prompt, stream=False,
        )
        return getattr(resp, "output_text", "") or ""
    finally:
        with contextlib.suppress(Exception):
            await proj.close()
        with contextlib.suppress(Exception):
            await credential.close()


async def generate(*, tenant_id: str, title: str, description: str, type: str,
                   prompt: str, user) -> ArtifactRecord:
    if type not in ALLOWED_TYPES:
        raise ValueError(f"invalid artifact type: {type}")
    html = await _generate_html(prompt, type, user=user)
    # create_draft re-validates (size + shape) before persisting.
    return create_draft(
        tenant_id=tenant_id, title=title, description=description, type=type,
        html=html, user=user,
    )
```

> **CLAUDE.md rule #1:** the `AIProjectClient` / `responses.create` surface is copied from the working `copilot._responses`. If it drifts, confirm against `learn.microsoft.com/azure/foundry` before pinning — do NOT invent signatures.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/services/artifacts.py apps/backend/eval/artifact_service_test.py
git commit -m "feat(artifacts): LLM generation (answer_direct pattern, self-contained HTML)"
```

---

## Chunk 4: Backend — API router (RBAC-gated)

### Task 9: `/artifacts` router — generate, list, get, content

**Files:**
- Create: `apps/backend/app/api/artifacts.py`
- Modify: `apps/backend/app/api/__init__.py:6` (import) + include
- Test: `apps/backend/eval/artifact_rbac_test.py` (new — asserts route→role wiring)

Because there is no HTTP test harness (no TestClient), the RBAC test asserts the **declared dependency wiring** by inspecting `router.routes` and confirming each route carries the expected `require_role` dependency. This catches the most common mistake (a write route left ungated).

- [ ] **Step 1: Write the failing test** (`eval/artifact_rbac_test.py`):

```python
"""Assert /artifacts routes declare the correct App Role gates.

Run (from apps/backend/):  uv run python -m eval.artifact_rbac_test

No HTTP harness exists in this repo, so we inspect the router's declared
dependencies. Guards against a write route accidentally left ungated.
"""
import sys

import app.core.settings as settings_mod

# Force auth ON so require_role dependencies are actually attached.
settings_mod.settings.entra_tenant_id = "t"
settings_mod.settings.entra_api_client_id = "c"
settings_mod.settings.artifact_store_backend = "memory"

from app.api import artifacts as art_api  # noqa: E402


def _roles_for(path: str, method: str) -> set[str]:
    for r in art_api.router.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
            roles: set[str] = set()
            for dep in r.dependant.dependencies:
                roles |= getattr(dep.call, "_required_roles", set())
            return roles
    return set()


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("generate requires Author/Admin",
          _roles_for("/artifacts/html/generate", "POST") == {"Author", "Admin"})
    check("approve requires Approver/Admin",
          _roles_for("/artifacts/html/{artifact_id}/approve", "POST") == {"Approver", "Admin"})
    check("list requires a role (any authenticated)",
          _roles_for("/artifacts/html", "GET") != set())

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

This requires `require_role` to tag its returned dependency with `_required_roles`. **Add that tag** in `apps/backend/app/core/auth.py` inside `require_role` (set `_check._required_roles = set(roles)` before returning) — a tiny, backward-compatible change enabling introspection.

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_rbac_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.artifacts'`.

- [ ] **Step 3a: Tag roles in `require_role`** (`apps/backend/app/core/auth.py`), just before `return _check`:

```python
    _check._required_roles = set(roles)  # for introspection/tests
    return _check
```

- [ ] **Step 3b: Create `apps/backend/app/api/artifacts.py`:**

```python
"""HTML Artifacts API — generate, list, view, and govern AI-generated HTML.

Thin router: HTTP + RBAC only; logic lives in app/services/artifacts.py.
Tenant partition comes from app.core.tenant.artifact_tenant_id().
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.core.auth import current_user, require_role
from app.core.tenant import artifact_tenant_id
from app.services import artifacts as svc

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

_author = Depends(require_role("Author", "Admin"))
_approver = Depends(require_role("Approver", "Admin"))
_reader = Depends(require_role("Reader", "Author", "Approver", "Admin"))


class GenerateBody(BaseModel):
    title: str
    description: str = ""
    type: str = "report"
    prompt: str


def _dto(rec) -> dict:
    return {
        "id": rec.id, "title": rec.title, "description": rec.description,
        "type": rec.type, "status": rec.status, "createdBy": rec.created_by,
        "createdAt": rec.created_at, "updatedAt": rec.updated_at,
        "approvedBy": rec.approved_by, "approvedAt": rec.approved_at,
        "version": rec.version, "contentHash": rec.content_hash,
    }


@router.post("/html/generate", dependencies=[_author])
async def generate_route(body: GenerateBody) -> dict:
    try:
        rec = await svc.generate(
            tenant_id=artifact_tenant_id(), title=body.title,
            description=body.description, type=body.type, prompt=body.prompt,
            user=current_user(),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _dto(rec)


@router.get("/html", dependencies=[_reader])
def list_route() -> dict:
    recs = svc.list_artifacts(artifact_tenant_id())
    return {"artifacts": [_dto(r) for r in recs]}


@router.get("/html/{artifact_id}", dependencies=[_reader])
def get_route(artifact_id: str) -> dict:
    try:
        rec = svc.get_artifact(artifact_tenant_id(), artifact_id, user=current_user())
    except svc.Forbidden:
        raise HTTPException(status_code=404, detail="not found")
    return _dto(rec)


@router.get("/html/{artifact_id}/content", dependencies=[_reader])
def content_route(artifact_id: str) -> Response:
    try:
        html = svc.get_content(artifact_tenant_id(), artifact_id, user=current_user())
    except svc.Forbidden:
        raise HTTPException(status_code=404, detail="not found")
    # Returned to the proxy, which hands it to the frontend for srcdoc injection.
    # NEVER rendered same-origin — the frontend puts it in a sandboxed iframe.
    # Defense-in-depth: `Content-Security-Policy: sandbox` makes the browser
    # sandbox the content even on a direct same-origin navigation — this closes
    # the local-dev gap where auth_enabled=False makes require_role a no-op.
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
```

- [ ] **Step 3c: Register in `apps/backend/app/api/__init__.py`** — add `artifacts` to the import on line 6 and `api_router.include_router(artifacts.router)`:

```python
from app.api import admin, artifacts, chat, copilot, evals, health, me, tickets
...
api_router.include_router(artifacts.router)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_rbac_test`
Expected: PASS. Also run the whole suite: `uv run python -m eval.artifact_store_test && uv run python -m eval.artifact_service_test`.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/api/artifacts.py apps/backend/app/api/__init__.py apps/backend/app/core/auth.py apps/backend/eval/artifact_rbac_test.py
git commit -m "feat(artifacts): /artifacts router — generate/list/get/content, RBAC-gated"
```

---

### Task 10: `/artifacts` router — lifecycle routes

**Files:**
- Modify: `apps/backend/app/api/artifacts.py`
- Test: `apps/backend/eval/artifact_rbac_test.py` (extend — already asserts approve gate; add request/reject/archive)

- [ ] **Step 1: Extend the RBAC test:**

```python
    check("request-approval requires Author/Admin",
          _roles_for("/artifacts/html/{artifact_id}/request-approval", "POST") == {"Author", "Admin"})
    check("reject requires Approver/Admin",
          _roles_for("/artifacts/html/{artifact_id}/reject", "POST") == {"Approver", "Admin"})
    check("archive requires Author/Admin",
          _roles_for("/artifacts/html/{artifact_id}/archive", "POST") == {"Author", "Admin"})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_rbac_test`
Expected: FAIL — the new paths return `set()`.

- [ ] **Step 3: Append lifecycle routes to `app/api/artifacts.py`:**

```python
def _act(fn, artifact_id: str):
    try:
        return _dto(fn(artifact_tenant_id(), artifact_id, user=current_user()))
    except svc.Forbidden:
        raise HTTPException(status_code=404, detail="not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/html/{artifact_id}/request-approval", dependencies=[_author])
def request_approval_route(artifact_id: str) -> dict:
    return _act(svc.request_approval, artifact_id)


@router.post("/html/{artifact_id}/approve", dependencies=[_approver])
def approve_route(artifact_id: str) -> dict:
    return _act(svc.approve, artifact_id)


@router.post("/html/{artifact_id}/reject", dependencies=[_approver])
def reject_route(artifact_id: str) -> dict:
    return _act(svc.reject, artifact_id)


@router.post("/html/{artifact_id}/archive", dependencies=[_author])
def archive_route(artifact_id: str) -> dict:
    return _act(svc.archive, artifact_id)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_rbac_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/api/artifacts.py apps/backend/eval/artifact_rbac_test.py
git commit -m "feat(artifacts): lifecycle routes — request-approval/approve/reject/archive"
```

---

### Task 11: Wire tests into CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the three artifact test modules** to the backend job (after the existing `eval.test_attribution` line, same `working-directory: apps/backend`):

```yaml
      - name: Artifact store tests
        working-directory: apps/backend
        run: |
          uv run python -m eval.artifact_store_test
          uv run python -m eval.artifact_service_test
          uv run python -m eval.artifact_rbac_test
```

- [ ] **Step 2: Verify locally** (CI can't be run here; run the exact commands):

Run: `cd apps/backend && uv run python -m eval.artifact_store_test && uv run python -m eval.artifact_service_test && uv run python -m eval.artifact_rbac_test`
Expected: all three print `PASS` and exit 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(artifacts): run artifact test modules in backend job"
```

---

## Chunk 5: Infra (Bicep)

### Task 12: Provision artifacts Blob container + Table + RBAC

**Files:**
- Modify: `infra/resources.bicep`
- Modify: `infra/containerapps.bicep`

Reference the existing storage patterns in `resources.bicep`: the storage account resource is named **`storage`** (declared at `:184`, outputs at `:435-436`), the blob service is **`blobService`** (`:197`), and the backend runs as the shared user-assigned identity **`appIdentity`** (its principal is `appIdentity.properties.principalId`, already used for other role assignments at `:273/:283/:293`). The file already defines `var roleStorageBlobDataContributor` (`:70`) — reuse it. `appIdentity` today has **no** Storage Blob/Table role, so these assignments are genuinely needed.

- [ ] **Step 1: Add the artifacts container + table to `infra/resources.bicep`** (under the existing `blobService` / after the corpus container):

```bicep
// Artifacts feature: private container for AI-generated HTML (never public).
resource artifactsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'artifacts'
  properties: {
    publicAccess: 'None'
  }
}

resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource artifactsTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  parent: tableService
  name: 'artifacts'
}
```

- [ ] **Step 2: Grant the backend UAMI data-plane roles** (mirror the existing role-assignment blocks). Add `Storage Blob Data Contributor` and `Storage Table Data Contributor` for the backend user-assigned identity principal:

Add a Table-role var next to the existing `var roleStorageBlobDataContributor` (`:70`):

```bicep
var roleStorageTableDataContributor = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
```

```bicep
// Backend identity (appIdentity) needs to read/write artifact blobs + table entries.
resource backendBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, appIdentity.id, roleStorageBlobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataContributor) // Storage Blob Data Contributor
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource backendTableContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, appIdentity.id, roleStorageTableDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageTableDataContributor) // Storage Table Data Contributor
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
```

> `appIdentity` is the shared UAMI both container apps run as. Confirm it is in scope in `resources.bicep` (it is — used at `:273/:283/:293`). Verify the exact symbol during implementation before pinning.

- [ ] **Step 3: Add outputs** to `resources.bicep` (mirror `AZURE_STORAGE_ACCOUNT` at `:435-436`):

```bicep
output ARTIFACT_BLOB_ACCOUNT_URL string = storage.properties.primaryEndpoints.blob
output ARTIFACT_STORE_ACCOUNT_URL string = storage.properties.primaryEndpoints.table
```

- [ ] **Step 4: Pass env vars into the backend container** in `infra/containerapps.bicep` (add to the backend app's `env` array, near where `AZURE_CLIENT_ID` is set at `:145`):

```bicep
        { name: 'ARTIFACT_STORE_BACKEND', value: 'table' }
        { name: 'ARTIFACT_CONTAINER', value: 'artifacts' }
        { name: 'ARTIFACT_TABLE', value: 'artifacts' }
        { name: 'ARTIFACT_BLOB_ACCOUNT_URL', value: artifactBlobAccountUrl }
        { name: 'ARTIFACT_STORE_ACCOUNT_URL', value: artifactStoreAccountUrl }
```

Add the two `param` declarations to `containerapps.bicep` and wire them from the `resources.bicep` outputs in `main.bicep` (follow how `storageAccountName` is already threaded, `containerapps.bicep:44-48`).

- [ ] **Step 5: Validate the Bicep compiles**

Run: `cd infra && az bicep build --file resources.bicep && az bicep build --file containerapps.bicep`
Expected: no errors (warnings about unused params are acceptable until wired).

> If `az` is unavailable in this environment, ask the user to run the validation via `! az bicep build --file infra/resources.bicep`. Do NOT claim it compiles without evidence (superpowers:verification-before-completion).

- [ ] **Step 6: Commit**

```bash
git add infra/resources.bicep infra/containerapps.bicep infra/main.bicep
git commit -m "infra(artifacts): private blob container + table + backend UAMI RBAC + env"
```

---

## Chunk 6: Frontend (bespoke page + sandbox viewer)

### Task 13: Proxy routes

**Files:**
- Create: `apps/frontend/app/api/artifacts/route.ts`
- Create: `apps/frontend/app/api/artifacts/[...path]/route.ts`

Mirror `app/api/tickets/route.ts` (forward the caller's `Authorization` verbatim, fail-soft 502). The catch-all must pass through `text/html` for the `/content` sub-route (all existing proxies are JSON-only — this is the first non-JSON one).

- [ ] **Step 1: Create `app/api/artifacts/route.ts`** (list + generate):

```ts
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/artifacts/html`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
    });
    if (!r.ok) {
      return NextResponse.json({ artifacts: [], error: `backend ${r.status}` }, { status: 502 });
    }
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json({ artifacts: [], error: "backend unreachable" }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/artifacts/html/generate`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: await req.text(),
    });
    const text = await r.text();
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 2: Create `app/api/artifacts/[...path]/route.ts`** (get/content/lifecycle — passes through the upstream `Content-Type` so `/content` returns `text/html`):

```ts
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

async function forward(req: NextRequest, path: string[], method: "GET" | "POST") {
  try {
    const auth = req.headers.get("authorization");
    const url = `${BACKEND}/artifacts/html/${path.join("/")}`;
    const r = await fetch(url, {
      method,
      cache: "no-store",
      headers: auth ? { Authorization: auth } : undefined,
      body: method === "POST" ? await req.text() : undefined,
    });
    const ct = r.headers.get("content-type") ?? "application/json";
    const buf = await r.arrayBuffer();
    return new NextResponse(buf, { status: r.status, headers: { "Content-Type": ct } });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(req, path, "GET");
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(req, path, "POST");
}
```

- [ ] **Step 3: Verify the frontend builds**

Run: `cd apps/frontend && npm run build`
Expected: build succeeds (route handlers compile). If build is too slow, at minimum `npx tsc --noEmit`.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/app/api/artifacts/route.ts "apps/frontend/app/api/artifacts/[...path]/route.ts"
git commit -m "feat(artifacts): frontend proxy routes (list/generate + catch-all w/ text/html passthrough)"
```

---

### Task 14: Sandbox viewer component

**Files:**
- Create: `apps/frontend/components/artifacts/SandboxViewer.tsx`

This is the **security-critical** component. It fetches HTML via `authedFetch` (bearer) and injects it as `srcdoc` into an iframe with `sandbox="allow-scripts"` and **no** `allow-same-origin`.

- [ ] **Step 1: Create `components/artifacts/SandboxViewer.tsx`:**

```tsx
"use client";
import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

/**
 * Renders an AI-generated HTML artifact in an isolated sandbox.
 *
 * SECURITY: the iframe uses `sandbox="allow-scripts"` WITHOUT `allow-same-origin`,
 * giving the content an opaque origin. It cannot read the app's cookies,
 * sessionStorage, DOM, or call same-origin APIs. The HTML is fetched here with
 * the bearer token (authedFetch) and passed via `srcDoc` — the iframe itself
 * never makes an authenticated request. Do NOT add `allow-same-origin`:
 * combined with `allow-scripts` it defeats the sandbox.
 */
export function SandboxViewer({ artifactId }: { artifactId: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await authedFetch(`/api/artifacts/${artifactId}/content`, {
          cache: "no-store",
        });
        if (!r.ok) throw new Error(`load failed (${r.status})`);
        const text = await r.text();
        if (alive) setHtml(text);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, [artifactId]);

  if (error) return <div className="pill pill-error">Preview error: {error}</div>;
  if (html === null) return <div className="pill">Loading preview…</div>;

  return (
    <iframe
      title="artifact-preview"
      srcDoc={html}
      sandbox="allow-scripts"
      style={{ width: "100%", height: "70vh", border: "1px solid var(--border, #333)", borderRadius: 8 }}
    />
  );
}
```

- [ ] **Step 2: Verify it typechecks**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/components/artifacts/SandboxViewer.tsx
git commit -m "feat(artifacts): SandboxViewer — srcdoc iframe, opaque origin (allow-scripts only)"
```

---

### Task 15: List view + generate form

**Files:**
- Create: `apps/frontend/components/artifacts/ArtifactsView.tsx`
- Create: `apps/frontend/app/artifacts/page.tsx`

Mirror `components/tickets/TicketsView.tsx` (client component, `authedFetch`, loading/empty states) and `app/tickets/page.tsx` (thin `<AppShell>` wrapper).

- [ ] **Step 1: Create `components/artifacts/ArtifactsView.tsx`** — list + a "generate" form:

```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { authedFetch } from "@/lib/auth/api";

type Artifact = {
  id: string; title: string; type: string; status: string;
  createdBy: string; updatedAt: string;
};

export function ArtifactsView() {
  const [items, setItems] = useState<Artifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [type, setType] = useState("report");

  async function load() {
    const r = await authedFetch("/api/artifacts", { cache: "no-store" });
    const data = await r.json();
    setItems(data.artifacts ?? []);
    if (data.error) setError(data.error);
  }

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
  }, []);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const r = await authedFetch("/api/artifacts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, prompt, type }),
      });
      if (!r.ok) throw new Error(`generate failed (${r.status})`);
      setTitle("");
      setPrompt("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <section style={{ marginBottom: 24 }}>
        <h3>Generate HTML artifact</h3>
        <input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="report">Report</option>
          <option value="presentation">Presentation</option>
          <option value="walkthrough">Walkthrough</option>
        </select>
        <textarea placeholder="Describe what to generate…" value={prompt}
          onChange={(e) => setPrompt(e.target.value)} rows={3} />
        <button disabled={busy || !title || !prompt} onClick={generate}>
          {busy ? "Generating…" : "Generate"}
        </button>
      </section>

      {error && <div className="pill pill-error">{error}</div>}

      <table>
        <thead>
          <tr><th>Title</th><th>Type</th><th>Status</th><th>Updated</th></tr>
        </thead>
        <tbody>
          {items.length === 0 && (
            <tr><td colSpan={4}>No artifacts yet.</td></tr>
          )}
          {items.map((a) => (
            <tr key={a.id}>
              <td><Link href={`/artifacts/${a.id}`}>{a.title}</Link></td>
              <td>{a.type}</td>
              <td><span className={`pill pill-${a.status}`}>{a.status}</span></td>
              <td>{a.updatedAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

> Match the exact markup/class conventions of `TicketsView.tsx` (pills, table styling) during implementation — the above is structural, adapt to the real design system.

- [ ] **Step 2: Create `app/artifacts/page.tsx`:**

```tsx
import { AppShell } from "@/components/shell/AppShell";
import { ArtifactsView } from "@/components/artifacts/ArtifactsView";

export default function ArtifactsPage() {
  return (
    <AppShell>
      <ArtifactsView />
    </AppShell>
  );
}
```

- [ ] **Step 3: Verify typecheck**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactsView.tsx apps/frontend/app/artifacts/page.tsx
git commit -m "feat(artifacts): artifacts list + generate form page"
```

---

### Task 16: Detail page + lifecycle actions

**Files:**
- Create: `apps/frontend/components/artifacts/ArtifactDetail.tsx`
- Create: `apps/frontend/app/artifacts/[id]/page.tsx`

- [ ] **Step 1: Create `components/artifacts/ArtifactDetail.tsx`** — metadata, lifecycle buttons (buttons call the proxy; the backend enforces roles, so a 403 surfaces as a disabled-after-error message), and the `<SandboxViewer>`:

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { SandboxViewer } from "./SandboxViewer";

type Artifact = {
  id: string; title: string; description: string; type: string; status: string;
  createdBy: string; approvedBy: string | null; version: number;
  contentHash: string | null; updatedAt: string;
};

export function ArtifactDetail({ id }: { id: string }) {
  const [a, setA] = useState<Artifact | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await authedFetch(`/api/artifacts/${id}`, { cache: "no-store" });
    if (!r.ok) {
      setError(`load failed (${r.status})`);
      return;
    }
    setA(await r.json());
  }, [id]);

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
  }, [load]);

  async function act(action: string) {
    setError(null);
    const r = await authedFetch(`/api/artifacts/${id}/${action}`, { method: "POST" });
    if (!r.ok) {
      setError(`${action} failed (${r.status})`);
      return;
    }
    await load();
  }

  if (error) return <div className="pill pill-error">{error}</div>;
  if (!a) return <div className="pill">Loading…</div>;

  return (
    <div>
      <h2>{a.title}</h2>
      <p>{a.description}</p>
      <div>
        <span className={`pill pill-${a.status}`}>{a.status}</span>
        {" "}v{a.version}
        {a.contentHash && <> · <code>{a.contentHash.slice(0, 12)}…</code></>}
      </div>

      <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
        {a.status === "draft" && (
          <button onClick={() => act("request-approval")}>Request approval</button>
        )}
        {a.status === "pending_approval" && (
          <>
            <button onClick={() => act("approve")}>Approve &amp; publish</button>
            <button onClick={() => act("reject")}>Reject</button>
          </>
        )}
        {(a.status === "published" || a.status === "draft") && (
          <button onClick={() => act("archive")}>Archive</button>
        )}
      </div>

      <SandboxViewer artifactId={a.id} />
    </div>
  );
}
```

- [ ] **Step 2: Create `app/artifacts/[id]/page.tsx`:**

```tsx
import { AppShell } from "@/components/shell/AppShell";
import { ArtifactDetail } from "@/components/artifacts/ArtifactDetail";

export default async function ArtifactDetailPage(
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return (
    <AppShell>
      <ArtifactDetail id={id} />
    </AppShell>
  );
}
```

- [ ] **Step 3: Verify typecheck**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 4: Commit**

```bash
git add "apps/frontend/components/artifacts/ArtifactDetail.tsx" "apps/frontend/app/artifacts/[id]/page.tsx"
git commit -m "feat(artifacts): artifact detail page — lifecycle actions + sandbox preview"
```

---

### Task 17: Navigation

**Files:**
- Modify: `apps/frontend/components/shell/AppShell.tsx:19-23` (WORKSPACE_NAV) and `:30-37` (TITLES)

- [ ] **Step 1: Add nav entries** to `WORKSPACE_NAV`:

```tsx
  { href: "/artifacts", label: "Artifacts", icon: "📦" },
```

and to `TITLES`:

```tsx
  "/artifacts": "Artifacts",
```

- [ ] **Step 2: Verify the app runs and the flow works end-to-end** — use the run/verify skill. Start backend (`ARTIFACT_STORE_BACKEND=memory`) + frontend, sign in, generate an artifact, open detail, confirm the sandbox preview renders and lifecycle buttons transition status.

Run (backend, from `apps/backend/`): `ARTIFACT_STORE_BACKEND=memory uv run uvicorn app.main:app --port 8000 --reload`
Run (frontend, from `apps/frontend/`): `npm run dev`
Expected: `/artifacts` lists items; generate creates a draft; detail shows the HTML in a sandboxed iframe; request-approval → approve flips status to `published` and shows a content hash.

> Use @verify to drive the real flow, not just typecheck. Confirm in the browser that the iframe has `sandbox="allow-scripts"` and no `allow-same-origin` (inspect element).

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/components/shell/AppShell.tsx
git commit -m "feat(artifacts): add Artifacts to workspace nav"
```

---

## Chunk 7: Wiki regeneration (closing step — run LAST)

The `deep-wiki tracks the code` gate (`eval.wiki_freshness_test`) compares each bundle's
`generatedAt` against the latest git commit touching that area (excluding `docs/wiki`). This
feature touches **backend, frontend, infra, and docs** — all four areas — so the committed
`docs/wiki/` bundles go stale the moment this work lands. Regenerate them as the **final step**,
against the fully-integrated code, so the gate goes green once with no rework.

> **MUST run after every other task is complete and merged-ready.** Regenerating earlier just
> re-stales the moment the next commit lands. This is why it is Chunk 7, not Chunk 1.

**Path: local Agent-Skills only — never Foundry.** Use the vendored deep-wiki plugin at
`.github/skills/deep-wiki/` (`agents/wiki-architect`, `wiki-writer`, `wiki-researcher`;
`commands/generate`, `build`, `page`). This is how `v0.3.0` was produced (`model: local-agent`)
and matches the standing preference (see `docs/wiki/README.md` §Regenerate, path B; ADR-012). Do
**not** use the `wiki_builder.py` Foundry pipeline.

### Task 18: Regenerate all four deep-wiki bundles → v0.4.0

**Files:**
- Regenerate: `docs/wiki/foundry-helpdesk-backend/v0.4.0/` (manifest.json + pages/*.md + llms.txt)
- Regenerate: `docs/wiki/foundry-helpdesk-frontend/v0.4.0/`
- Regenerate: `docs/wiki/foundry-helpdesk-infra/v0.4.0/`
- Regenerate: `docs/wiki/foundry-helpdesk-docs/v0.4.0/`
- Remove: the superseded `v0.3.0/` bundles (v0.2.0 → v0.3.0 dropped the prior version; follow that convention)
- Verify: `apps/backend/eval/wiki_freshness_test.py` (gate) + the build-fidelity gate

- [ ] **Step 1: Confirm this is truly the last step** — all of Tasks 1–17 committed, the branch
  is at the final integrated state. Regenerating against anything less will re-stale.

- [ ] **Step 2: Regenerate each area via the deep-wiki local skill** (one faithful pass per area,
  parallelizable). For each of the 4 areas, invoke the vendored deep-wiki generator to read the
  real source and write a cited bundle, e.g.:

  > "Regenerate the deep-wiki for area `apps/backend` following the `.github/skills/deep-wiki`
  > `wiki-architect` + `wiki-writer` skills, in the ingest bundle format (`manifest.json` +
  > `pages/page-N.md` + `llms.txt`), version **v0.4.0**, `model: local-agent`, language `pt-br`,
  > with linked citations and the **≥80% build-fidelity gate** (every cited path must resolve to a
  > real source file). Cover the new HTML Artifacts feature: the `/artifacts` router + service,
  > `ArtifactStore`/`ArtifactContentStore`, the srcDoc sandbox viewer, and the Bicep additions."

  Areas + their source roots (from `eval/wiki_freshness_test.py` `_AREA`):
  `apps/backend`, `apps/frontend`, `infra`, `docs`. For the cross-cutting `docs` bundle, resolve
  citations against the repo root (the `--fidelity-root` behavior noted in `docs/wiki/README.md`).

- [ ] **Step 3: Stamp `generatedAt` and `componentVersion`** — each `manifest.json` must have
  `componentVersion: "v0.4.0"`, `model: "local-agent"`, and a fresh `generatedAt` (current UTC,
  newer than the latest source commit). Update the bundle table + "What this dogfood surfaced"
  section in `docs/wiki/README.md` to v0.4.0.

- [ ] **Step 4: Verify the freshness gate passes**

  Run: `cd apps/backend && uv run python -m eval.wiki_freshness_test`
  Expected: `✅ Wiki fresh — all 4 bundle(s) newer than their source.`

- [ ] **Step 5: Verify build-fidelity** (≥80% of cited paths resolve to real files) per
  `eval/assurance.yaml` — the same gate that guards generation. Fix any dangling citations.

- [ ] **Step 6: Commit**

```bash
git add docs/wiki/ docs/wiki/README.md
git commit -m "docs(wiki): regenerate deep-wiki v0.4.0 (HTML Artifacts feature; local-agent path)"
```

> **Ingest is separate and manual** (not part of this gate): getting the bundles into the Foundry
> `selfwiki-si-kb` is `uv run python -m app.knowledge.ingest_docbundles --selfwiki` (needs Azure
> sign-in + data-plane roles). Note it in the PR so a maintainer can run it; the freshness gate
> and merge do **not** require it.

---

## Definition of done

- [ ] All three backend test modules pass: `uv run python -m eval.artifact_store_test && uv run python -m eval.artifact_service_test && uv run python -m eval.artifact_rbac_test`.
- [ ] CI runs them (Task 11).
- [ ] Bicep compiles (Task 12).
- [ ] Frontend typechecks and builds; `/artifacts` end-to-end flow verified in the browser (Task 17).
- [ ] The sandbox iframe uses `allow-scripts` **without** `allow-same-origin` (verified by inspection).
- [ ] A write route left ungated would fail `artifact_rbac_test` (the guard works — verify by temporarily removing a gate and seeing red, then restore).
- [ ] Security review: run @security-review on the branch before merge (untrusted-HTML feature).
- [ ] **Wiki regenerated (Task 18)** — `uv run python -m eval.wiki_freshness_test` prints `✅ Wiki fresh`; all four v0.4.0 bundles committed via the local deep-wiki path.

## Notes for the executor

- **CLAUDE.md rule #1** — the `AIProjectClient` / `responses.create` surface (Task 8) is copied from the working `app/services/copilot.py`. If it drifts, verify against Foundry docs before pinning; do not invent signatures.
- **CLAUDE.md rule #4** does not apply here (that's the resolver's citation policy; artifacts are not resolver output).
- **`self_hosted` default** — `artifact_tenant_id()` returns `"default"` when there's no per-request tenant. This is correct for today's default mode; in `shared` mode it becomes the resolved tid automatically.
- **No pytest in CI** — a couple of dormant `test_*.py` files use pytest, but pytest is not a declared dep and CI never runs them. All tests in this plan are `main() -> int` modules run via `uv run python -m eval.<name>`. Do not write `uv run pytest`.
- **Next version skew** — `package.json` says Next 16, installed is 15.5.19. The `await params` signature used here works on both; if the build behaves oddly, reconcile the version first.
