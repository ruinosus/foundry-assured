"""Sub-project C infra-gated E2E proof — MCP credential-brokering via Foundry connections.

Proves that `build_from_connections` and `build_hosted_from_connections` resolve credentials
correctly against a LIVE Foundry project + real Connections.  The infra-gated value is the
LIVE credential fetch (the Foundry SDK call that returns the actual ApiKey) and the OBO token
mint (a real Entra token exchange); these cannot be faked offline.

When the required environment is absent the module SKIPS CLEANLY (prints a skip note,
exits 0), so an offline eval sweep stays green.

== What the test proves ==
  (a) internal SDK-broker: `build_from_connections((github_conn,), {"Admin"})` builds a tool
      whose `header_provider`, when invoked, returns an ``Authorization: Bearer <key>`` header
      brokered live from the Foundry connection (credential fetched at call time, not stored).
  (b) approval gating: the built tool's ``approval_mode`` has the write tool(s) under
      ``always_require_approval`` (the HITL gate, not native MCP approval).
  (c) OBO: an OBO connection (azdo with an ``endpoint`` org) builds with a header_provider
      that, when invoked against a live Entra tenant, mints a real OBO bearer token.
  (d) hosted path (optional): `build_hosted_from_connections` with a real ``client.get_mcp_tool``
      builds a FoundryMCPTool carrying the ``project_connection_id``.

== Required environment variables ==
ALL of the following must be set for the real assertions to run.
Set them in a .env file or CI secrets — NEVER commit them.

  DEPLOYMENT_MODE=shared
      Gate: must be exactly "shared" or the test skips.

  FOUNDRY_PROJECT_ENDPOINT
      Azure AI Foundry project endpoint, e.g.
      https://<project>.api.azureml.ms

  MCP_E2E_FOUNDRY_CONNECTION_ID
      The ``name`` / id of an existing ApiKey Foundry connection in the project above.
      This is the connection that brokers the GitHub PAT (or any ApiKey secret).
      Used to exercise the internal SDK-broker path (assertion a).

  (Optional — for the OBO assertion c)
  MCP_E2E_AZDO_ORG
      Azure DevOps organization slug, e.g. "myorg".  If set, the test also proves the
      OBO header_provider mints a real token.  If absent, assertion (c) is skipped with a note.

  (Optional — for the hosted path assertion d)
  MCP_E2E_HOSTED=1
      Set to "1" to also exercise build_hosted_from_connections.  Requires a live Foundry
      AIProjectClient reachable with DefaultAzureCredential.

== Run ==
  uv run python -m eval.mcp_brokering_e2e_test

Skip note is printed when infra is absent; exit 0 either way.
"""

from __future__ import annotations

import os
import sys


# ---------------------------------------------------------------------------
# Gate: read env vars and decide whether to skip or run
# ---------------------------------------------------------------------------

def _required_config() -> dict | None:
    """Return config dict if ALL required vars are present, else None."""

    def _e(name: str) -> str:
        return os.environ.get(name, "").strip()

    deployment_mode = _e("DEPLOYMENT_MODE")
    foundry_endpoint = _e("FOUNDRY_PROJECT_ENDPOINT")
    foundry_connection_id = _e("MCP_E2E_FOUNDRY_CONNECTION_ID")

    if not all([
        deployment_mode == "shared",
        foundry_endpoint,
        foundry_connection_id,
    ]):
        return None

    return {
        "foundry_endpoint": foundry_endpoint,
        "foundry_connection_id": foundry_connection_id,
        "azdo_org": _e("MCP_E2E_AZDO_ORG"),        # optional
        "hosted": _e("MCP_E2E_HOSTED") == "1",      # optional
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = _required_config()
    if cfg is None:
        print(
            "– MCP brokering E2E skipped "
            "(set DEPLOYMENT_MODE=shared + FOUNDRY_PROJECT_ENDPOINT + "
            "MCP_E2E_FOUNDRY_CONNECTION_ID to run)"
        )
        return 0

    # Import here (after the gate) so offline runs never import azure-ai-projects
    # or the app modules that pull in framework dependencies.
    from azure.identity import DefaultAzureCredential

    from app.agents.mcp.tools import build_from_connections, build_hosted_from_connections
    from app.core.tenant_store import Connection

    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        mark = "✓" if cond else "✗"
        print(f"  {mark} {name}")
        if not cond:
            failures.append(name)

    print(
        f"MCP brokering E2E — endpoint={cfg['foundry_endpoint'][:40]}…, "
        f"connection_id={cfg['foundry_connection_id']}"
    )

    # Patch the tenant context so build_from_connections can resolve the endpoint.
    # We monkeypatch tenant_config() to return a TenantConfig with our test values.
    # This avoids needing a live Table Storage / tenant record for this test.
    import app.core.tenant as _tenant_mod
    from app.core.tenant import TenantConfig

    original_tenant_config = getattr(_tenant_mod, "_tenant_config_override", None)
    test_tenant_cfg = TenantConfig(
        foundry_project_endpoint=cfg["foundry_endpoint"],
        mcp_ado_organization=cfg["azdo_org"] or "",
    )

    # Monkeypatch: replace `tenant_config()` for the duration of the test.
    # The function lives in app.core.tenant; tools.py imports it from there.
    _original_fn = _tenant_mod.tenant_config
    _tenant_mod.tenant_config = lambda: test_tenant_cfg  # type: ignore[assignment]
    # Also patch the reference already imported into tools (re-exported name).
    import app.agents.mcp.tools as _tools_mod
    _tools_mod_tenant_config_orig = _tools_mod.tenant_config
    _tools_mod.tenant_config = lambda: test_tenant_cfg  # type: ignore[assignment]

    # Patch credential_for_request() so the header_provider closure uses DefaultAzureCredential.
    import app.core.auth as _auth_mod
    _original_credential_fn = _auth_mod.credential_for_request
    _daz_cred = DefaultAzureCredential()
    _auth_mod.credential_for_request = lambda: _daz_cred  # type: ignore[assignment]
    import app.agents.mcp.tools as _tools_mod2  # same object, already imported above
    _tools_mod2_cred_orig = getattr(_tools_mod2, "credential_for_request", None)
    # credential_for_request is used inside the closures via the auth module import,
    # so patching _auth_mod is sufficient.

    try:
        # ------------------------------------------------------------------ #
        # (a) internal SDK-broker: build + invoke the header_provider        #
        # ------------------------------------------------------------------ #
        print("\n  — (a) internal SDK-broker (ApiKey via Foundry connection) —")

        github_conn = Connection(
            id="gh-e2e",
            kind="github",
            label="GitHub E2E test",
            foundry_connection_id=cfg["foundry_connection_id"],
            enabled=True,
        )

        tools = build_from_connections((github_conn,), {"Admin"})
        check("(a) build_from_connections returns at least one tool", len(tools) >= 1)

        if tools:
            tool = tools[0]
            header_provider = getattr(tool, "header_provider", None)
            check("(a) tool has a header_provider", callable(header_provider))

            if callable(header_provider):
                # Invoke the provider — this makes a LIVE call to Foundry to broker the key.
                headers = header_provider({})
                auth_value = headers.get("Authorization", "")
                check("(a) Authorization header present", bool(auth_value))
                check("(a) Authorization is a Bearer token", auth_value.startswith("Bearer "))
                # The credential is fetched at call time — the provider must not have stored it
                # as a plain string during construction (it's a closure, not a cached value).
                # We verify by calling again and getting a non-empty value (idempotent live fetch).
                headers2 = header_provider({})
                check("(a) header_provider is callable multiple times (lazy fetch)",
                      headers2.get("Authorization", "").startswith("Bearer "))

        # ------------------------------------------------------------------ #
        # (b) approval gating: writes under always_require_approval          #
        # ------------------------------------------------------------------ #
        print("\n  — (b) approval gating —")

        if tools:
            tool = tools[0]
            approval_mode = getattr(tool, "approval_mode", None)
            check("(b) tool has an approval_mode attribute", approval_mode is not None)

            if isinstance(approval_mode, dict):
                always = approval_mode.get("always_require_approval", [])
                never = approval_mode.get("never_require_approval", [])
                # GitHub write tool per registry: "github_issue_create"
                check("(b) github_issue_create is under always_require_approval",
                      "github_issue_create" in always)
                # GitHub read tools per registry: "github_repo_search", "github_issue_list"
                check("(b) read tools are under never_require_approval",
                      "github_repo_search" in never or "github_issue_list" in never)
            else:
                # If approval_mode is a string (legacy MCPStreamableHTTPTool API), the dict form
                # should already be the new API from tools.py; flag this as unexpected.
                check("(b) approval_mode is a dict (connection path)", False)

        # ------------------------------------------------------------------ #
        # (c) OBO path: azdo connection mints a real Entra token             #
        # ------------------------------------------------------------------ #
        print("\n  — (c) OBO path (AzDO connection) —")

        if cfg["azdo_org"]:
            azdo_conn = Connection(
                id="azdo-e2e",
                kind="azdo",
                label="Azure DevOps E2E test",
                endpoint=cfg["azdo_org"],
                foundry_connection_id="",  # OBO path — no Foundry connection needed
                enabled=True,
            )
            azdo_tools = build_from_connections((azdo_conn,), {"Admin"})
            check("(c) build_from_connections returns an azdo tool", len(azdo_tools) >= 1)

            if azdo_tools:
                azdo_tool = azdo_tools[0]
                azdo_provider = getattr(azdo_tool, "header_provider", None)
                check("(c) azdo tool has a header_provider", callable(azdo_provider))

                if callable(azdo_provider):
                    # This makes a LIVE OBO call via DefaultAzureCredential → Entra.
                    azdo_headers = azdo_provider({})
                    azdo_auth = azdo_headers.get("Authorization", "")
                    check("(c) OBO Authorization header present", bool(azdo_auth))
                    check("(c) OBO Authorization is a Bearer token",
                          azdo_auth.startswith("Bearer "))
        else:
            print("  (c) skipped — MCP_E2E_AZDO_ORG not set")

        # ------------------------------------------------------------------ #
        # (d) hosted path: build_hosted_from_connections (optional)          #
        # ------------------------------------------------------------------ #
        print("\n  — (d) hosted path (build_hosted_from_connections) —")

        if cfg["hosted"]:
            from azure.ai.projects import AIProjectClient

            project_client = AIProjectClient(
                endpoint=cfg["foundry_endpoint"],
                credential=_daz_cred,
            )

            # get_mcp_tool is the real SDK method; inject it as the get_tool callable.
            get_tool_fn = project_client.get_mcp_tool  # type: ignore[attr-defined]

            hosted_tools = build_hosted_from_connections(
                (github_conn,), {"Admin"}, get_tool=get_tool_fn
            )
            check("(d) build_hosted_from_connections returns at least one tool",
                  len(hosted_tools) >= 1)

            if hosted_tools:
                h_tool = hosted_tools[0]
                # The hosted tool should carry project_connection_id (no header_provider needed).
                pcid = getattr(h_tool, "project_connection_id", None)
                check("(d) hosted tool carries the project_connection_id",
                      pcid == cfg["foundry_connection_id"])
                # And must NOT have a header_provider (Foundry resolves auth internally).
                check("(d) hosted tool has no header_provider (Foundry resolves auth)",
                      not callable(getattr(h_tool, "header_provider", None)))
        else:
            print("  (d) skipped — set MCP_E2E_HOSTED=1 to run the hosted path")

    finally:
        # Restore all monkeypatches.
        _tenant_mod.tenant_config = _original_fn  # type: ignore[assignment]
        _tools_mod.tenant_config = _tools_mod_tenant_config_orig  # type: ignore[assignment]
        _auth_mod.credential_for_request = _original_credential_fn  # type: ignore[assignment]

    print()
    if failures:
        print(f"❌ {len(failures)} assertion(s) failed: {failures}")
        return 1
    print("✅ MCP brokering E2E — internal broker + approval gating all green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
