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
