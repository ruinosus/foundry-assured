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
    check("get requires a role (any authenticated)",
          _roles_for("/artifacts/html/{artifact_id}", "GET") != set())
    check("content requires a role (any authenticated)",
          _roles_for("/artifacts/html/{artifact_id}/content", "GET") != set())
    check("request-approval requires Author/Admin",
          _roles_for("/artifacts/html/{artifact_id}/request-approval", "POST") == {"Author", "Admin"})
    check("reject requires Approver/Admin",
          _roles_for("/artifacts/html/{artifact_id}/reject", "POST") == {"Approver", "Admin"})
    check("archive requires Author/Admin",
          _roles_for("/artifacts/html/{artifact_id}/archive", "POST") == {"Author", "Admin"})

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
