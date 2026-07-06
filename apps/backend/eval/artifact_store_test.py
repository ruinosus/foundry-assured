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

    from app.artifacts.store import InMemoryContentStore

    content = InMemoryContentStore()
    path = f"default/{aid}/v1/index.html"
    content.put(path, "<html>hi</html>")
    check("content round-trips", content.get(path) == "<html>hi</html>")
    check("missing content is None", content.get("nope") is None)

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
