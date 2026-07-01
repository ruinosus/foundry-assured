"""Infra-gated E2E for the /platform-hosted Invocations bridge.

Mirrors the skip-clean pattern of `mcp_brokering_e2e_test.py`: offline (no deployed platform
hosted agent) it SKIPS CLEANLY (prints a note, exits 0). With a real deployed agent + endpoint
it WOULD drive `stream_platform_agui` against the live Invocations endpoint and assert a
non-error terminal event.

== Why the live body is a placeholder NOW ==
Per Task 0, the Invocations SSE request/response envelope is NOT determinable offline
(`azure-ai-projects` 2.2.0 exposes only `protocols/openai`). The bridge ships as a clean-error
skeleton (project rule #1: never fabricate an SDK contract). The real raw-SSE streaming +
its assertions land in D-packaging, against a deployed agent — the infra-gated E2E is its
real test. So the live branch below is a clearly marked TODO(D-packaging) placeholder; the
key requirement NOW is the skip-clean offline path.

== Required environment ==
A deployed platform hosted agent reachable via a configured FOUNDRY_PROJECT_ENDPOINT.
Set FOUNDRY_PROJECT_ENDPOINT (+ DefaultAzureCredential) to opt in; absent ⇒ skip.

== Run ==
  uv run python -m eval.platform_hosted_e2e_test

Skip note is printed when infra is absent; exit 0 either way.
"""

from __future__ import annotations

import sys

from app.core.tenant import tenant_config


def main() -> int:
    cfg = tenant_config()
    if not (cfg.foundry_project_endpoint or "").strip():
        print("⏭ skipped (no deployed platform hosted agent)")
        return 0

    # ------------------------------------------------------------------ #
    # Live path — infra present. Deferred to D-packaging.                 #
    # ------------------------------------------------------------------ #
    # TODO(D-packaging): drive stream_platform_agui against the live Invocations endpoint and
    # assert a non-error terminal event (RUN_FINISHED, not RUN_ERROR). The Invocations SSE
    # contract is not verified offline (Task 0), so this stays a placeholder until D-packaging
    # implements + verifies the real streaming POST against a deployed agent.
    #
    # NAMESPACE NOTE: to point the bridge at a configured endpoint, patch
    #   app.services.hosted.tenant_config  (the IMPORTING namespace — hosted.py imports the
    #   symbol `from app.core.tenant import tenant_config`, so rebinding app.core.tenant's
    #   attribute alone won't affect the already-imported reference inside hosted.py),
    # NOT app.core.tenant.tenant_config.
    print(
        "⏭ skipped (platform hosted Invocations E2E deferred to D-packaging — "
        "live streaming contract not verified offline; see Task 0)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
