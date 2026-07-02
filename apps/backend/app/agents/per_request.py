"""Generic per-request agent proxy — builds its inner agent on every call.

`add_agent_framework_fastapi_endpoint(agent=...)` wants a `SupportsAgentRun` *instance*, not a
factory. In self_hosted/dedicated the grounded domains (cockpit, selfwiki) build once at boot
under the single-tenant config. In **shared** mode no tenant is resolved at boot, so the build —
which reads `tenant_config()` — can't run until a request has resolved its tenant (via the auth +
`require_domain` dependencies). This proxy defers the build to request time: each `.run()` calls
the builder fresh, so it reads THIS request's tenant config.

The platform domain reuses this with name/description overrides (its builder also filters MCP
tools by caller role/OBO). `SupportsAgentRun` is a `@runtime_checkable` Protocol whose members include the
data attributes `id`/`name`/`description` AND `run`/`create_session`/`get_session`; `isinstance`
checks the attributes too, so the class carries `id`/`name`/`description` and delegates the three
methods. The AG-UI adapter builds its own `AgentSession` on the default
`use_service_session=False` path, so `create_session`/`get_session` are protocol-only.
"""

from __future__ import annotations

from collections.abc import Callable

from agent_framework import Agent


class PerRequestAgent:
    """A `SupportsAgentRun` proxy that rebuilds `builder()` on each delegated call.

    The advertised `name` defaults to `agent_id` (e.g. "cockpit") — an intentional shared-mode
    cosmetic default: the inner agent's richer name (e.g. "CockpitExpert") isn't available without
    building it, which we deliberately defer to request time, so we don't build just to read a name
    (self_hosted is unaffected — it serves the eagerly-built agent with its full name).
    """

    def __init__(self, agent_id: str, builder: Callable[[], Agent],
                 name: str | None = None, description: str | None = None) -> None:
        self.id = agent_id
        self.name = name or agent_id
        self.description = description or f"Per-request grounded agent for the {agent_id} domain."
        self._builder = builder

    def run(self, *args, **kwargs):  # returns Awaitable | ResponseStream — pass through
        return self._builder().run(*args, **kwargs)

    def create_session(self, *args, **kwargs):  # protocol-only (see module docstring)
        return self._builder().create_session(*args, **kwargs)

    def get_session(self, *args, **kwargs):  # protocol-only (see module docstring)
        return self._builder().get_session(*args, **kwargs)
