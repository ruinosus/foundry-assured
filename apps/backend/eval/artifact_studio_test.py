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

    from agent_framework._tools import FunctionTool

    from app.agents.artifacts_studio import update_artifact

    # update_artifact is an agent-framework @tool with a flat `html` string arg (required for the
    # predictive partial-delta extractor to stream — see the agent module comment).
    check("update_artifact is a FunctionTool named update_artifact",
          isinstance(update_artifact, FunctionTool) and update_artifact.name == "update_artifact")

    # FunctionTool.parameters() is a METHOD returning a JSON-schema dict (verified against the
    # installed SDK); the arg names live under ["properties"] — NOT top-level (which also has a
    # "type" key that would false-pass). Call it and read properties.
    schema = update_artifact.parameters()
    props = set(schema.get("properties", {}).keys())
    check("update_artifact takes html/title/type/skill", {"html", "title", "type", "skill"} <= props)

    # --- build_studio_agent wires the SkillsProvider + tools ---
    # Capture as_agent's kwargs (auth off → credential_for_request() is DefaultAzureCredential, so
    # build_studio_agent() is construction-only: no network). as_agent is inherited from
    # BaseChatClient; patch it on FoundryChatClient and restore in finally.
    import app.agents.artifacts_studio as sm
    from agent_framework import SkillsProvider
    captured: dict = {}
    orig_as_agent = sm.FoundryChatClient.as_agent
    sm.FoundryChatClient.as_agent = lambda self, **kw: captured.update(kw) or object()
    try:
        sm.build_studio_agent()
    finally:
        sm.FoundryChatClient.as_agent = orig_as_agent
    cps = captured.get("context_providers", [])
    check("studio wires a SkillsProvider", any(isinstance(c, SkillsProvider) for c in cps))
    check("studio tools include update_artifact", sm.update_artifact in (captured.get("tools") or []))

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
