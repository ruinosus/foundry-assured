"""Build the app under a fixed env profile and print its route surface as JSON.

Run as a subprocess by `routes_snapshot_test.py`, once per profile. It is a separate
process on purpose: `settings` and the domain registry are read at import time, so
re-importing under a second env in the same interpreter would capture leftover state
from the first — the exact failure this snapshot exists to catch.

    uv run python -m tests.smoke._capture_routes self_hosted
"""

from __future__ import annotations

import json
import os
import sys

# Synthetic, non-secret values. They exist so the eager factories can be constructed;
# every heavy object is replaced below, so nothing here reaches the network.
PROFILES = {
    "self_hosted": {
        "DEPLOYMENT_MODE": "self_hosted",
        "MCP_ENABLED": "true",
        "FOUNDRY_PROJECT_ENDPOINT": "https://snapshot.invalid/api/projects/snapshot",
        "AZURE_SEARCH_ENDPOINT": "https://snapshot.invalid",
        "AZURE_SEARCH_KNOWLEDGE_BASE": "snapshot-kb",
    },
    # ADR-020: the LangGraph domain mounts only with an Azure OpenAI endpoint, so a profile
    # that sets one is the only way the snapshot can prove /oncall exists at all.
    "self_hosted_oncall": {
        "DEPLOYMENT_MODE": "self_hosted",
        "MCP_ENABLED": "true",
        "FOUNDRY_PROJECT_ENDPOINT": "https://snapshot.invalid/api/projects/snapshot",
        "AZURE_SEARCH_ENDPOINT": "https://snapshot.invalid",
        "AZURE_SEARCH_KNOWLEDGE_BASE": "snapshot-kb",
        "AZURE_OPENAI_ENDPOINT": "https://snapshot.invalid",
    },
    "shared": {
        "DEPLOYMENT_MODE": "shared",
        "MCP_ENABLED": "true",
        "FOUNDRY_PROJECT_ENDPOINT": "https://snapshot.invalid/api/projects/snapshot",
    },
}


def main() -> int:
    profile = sys.argv[1]
    # A profile must be HERMETIC, not merely additive. `settings` reads `.env` from the cwd,
    # so a developer's local file was enough to change the captured surface: setting
    # AZURE_OPENAI_ENDPOINT there mounted /oncall inside the `self_hosted` profile, whose
    # entire job is to prove /oncall does NOT mount without one. The snapshot then reported a
    # route change that existed only on that machine.
    #
    # Blanking every key any profile mentions makes each profile mean what it says: the keys
    # it omits are absent, not inherited. Blank rather than deleted because `.env` is read
    # after this and would put them back.
    for key in {k for values in PROFILES.values() for k in values}:
        os.environ[key] = ""
    for key, value in PROFILES[profile].items():
        os.environ[key] = value

    # Import and neutralize the heavy factories BEFORE app.main runs mount_domains().
    # The mount helpers import these lazily from the module, so patching the module
    # attribute here is what the mount actually sees.
    from app import registry as domains
    import app.modules.grounded.internal.concierge as concierge
    import app.modules.platform_ops.internal.platform as platform
    from app.modules.helpdesk.internal import graph, stream_fix

    concierge.build_concierge_agent = lambda: object()
    platform.platform_agent_proxy = object()
    graph.build_helpdesk_workflow = lambda *a, **k: object()
    stream_fix.OrderedAgentFrameworkWorkflow = lambda **k: object()

    real_adapter = domains.add_agent_framework_fastapi_endpoint

    def adapter(app, *, agent=None, path=None, dependencies=None, **kw):
        # Register a real route so the adapter's paths show up in the snapshot, without
        # building the AG-UI endpoint (which would need a live agent).
        app.add_api_route(path, lambda: None, methods=["POST"], dependencies=dependencies)

    domains.add_agent_framework_fastapi_endpoint = adapter
    try:
        from app.main import app
    finally:
        domains.add_agent_framework_fastapi_endpoint = real_adapter

    routes = sorted(
        {(method, route.path) for route in app.routes for method in getattr(route, "methods", ())}
    )
    print(json.dumps([[m, p] for m, p in routes], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
