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

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except ValidationError:
        return True


def _raises_forbidden(fn) -> bool:
    import app.services.artifacts as svc

    try:
        fn()
        return False
    except svc.Forbidden:
        return True


def _raises_value(fn) -> bool:
    try:
        fn()
        return False
    except ValueError:
        return True


if __name__ == "__main__":
    sys.exit(main())
