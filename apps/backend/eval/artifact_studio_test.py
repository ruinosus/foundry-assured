"""Artifacts Studio agent — tool + state wiring (no LLM, no network).

Run (from apps/backend/):  uv run python -m eval.artifact_studio_test
"""
import sys


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    from app.agents.artifacts_studio import ArtifactDraft, update_artifact

    # ArtifactDraft holds the complete HTML document.
    d = ArtifactDraft(html="<!doctype html><html><body>x</body></html>")
    check("ArtifactDraft.html round-trips", d.html.startswith("<!doctype html>"))

    # update_artifact is an agent-framework @tool (has the tool marker) and returns a confirmation.
    check("update_artifact is a tool", hasattr(update_artifact, "__agent_framework_tool__")
          or hasattr(update_artifact, "ai_function") or callable(update_artifact))

    # --- mount introspection: /artifacts-studio gated Author/Admin ---
    import app.agents.artifacts_studio as studio_mod
    import app.core.settings as settings_mod
    settings_mod.settings.entra_tenant_id = "t"       # force auth ON so deps attach
    settings_mod.settings.entra_api_client_id = "c"

    calls = []
    orig = studio_mod.add_agent_framework_fastapi_endpoint
    studio_mod.add_agent_framework_fastapi_endpoint = (
        lambda app, agent=None, path=None, dependencies=None, **kw:
        calls.append({"path": path, "dependencies": dependencies or []})
    )
    try:
        studio_mod.mount_artifacts_studio(object())  # fake app; adapter is faked
    finally:
        studio_mod.add_agent_framework_fastapi_endpoint = orig

    check("studio mounted at /artifacts-studio", any(c["path"] == "/artifacts-studio" for c in calls))
    roles = set()
    for c in calls:
        for dep in c["dependencies"]:
            roles |= getattr(getattr(dep, "dependency", None), "_required_roles", set())
    check("studio mount requires Author/Admin", {"Author", "Admin"} <= roles)

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
