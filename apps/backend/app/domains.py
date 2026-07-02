"""Backend domain registry + one mount loop that dispatches by `kind`.

Mirrors the frontend registry (apps/frontend/lib/domains.ts): four domains, each with a
`kind` — `workflow` (helpdesk: triage→retrieve→resolve→escalate over AG-UI), `grounded`
(cockpit/selfwiki: cited Q&A via the `stream_grounded` archetype), `tool` (platform: MCP-
driven ops). Adding a domain = one `DomainSpec` row here (+ its agent/KB on the backend).

`mount_domains(app)` walks `_domains()` once and dispatches by kind, so the wiring lives in
ONE place instead of split across main.py (AG-UI adapter) and api/chat.py (router endpoints).

Notes:
- `_domains()` reads `tenant_config()` LAZILY — no import-time side effects (import app.domains
  is free). ACL is DATA (RULE #6): the registry only carries `acl_group_map` (name→objectID);
  no classification logic lives here.
- `_domain_deps` is the canonical domain-gate helper (moved here from main.py; api/chat.py's
  `_hosted_deps` is its duplicate). self_hosted/dedicated → exactly auth_dependencies(), byte-
  identical to today; only shared mode adds the per-tenant entitlement gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse

from app.core.auth import auth_dependencies
from app.core.settings import settings
from app.core.tenant import require_domain, tenant_config


@dataclass(frozen=True)
class DomainSpec:
    """One registry row — the backend twin of a frontend Domain (domains.ts).

    ACL is DATA (RULE #6): `acl_group_map` is a name→objectID dict carried as data; the
    registry never classifies. A grounded spec MUST resolve to a `kb_name` OR a `search_index`
    (else the retrieval fallback would hit `.../indexes/None/docs/search`) — enforced in
    __post_init__.
    """

    id: str
    kind: Literal["grounded", "workflow", "tool"]
    instructions: str = ""
    kb_name: str | None = None
    ks_name: str | None = None  # KB's knowledge-source name (native path); None → defaults to kb_name
    search_index: str | None = None
    search_endpoint: str = ""
    acl_group_map: dict | None = None  # name→objectID; None/empty → no ACL trim (no-op)
    hosted_agent_name: str | None = None

    def __post_init__(self) -> None:
        # A grounded domain with neither a KB nor a search index would fall through to
        # `.../indexes/None/docs/search` in retrieval — fail fast at registry build instead.
        if self.kind == "grounded" and not (self.kb_name or self.search_index):
            raise ValueError(
                f"grounded domain '{self.id}' must set kb_name or search_index"
            )


def _domains() -> list[DomainSpec]:
    """The four domain specs, built from the current request's tenant config (read LAZILY here —
    NOT at import). Mirrors domains.ts row-for-row."""
    from app.agents.prompts import COCKPIT_INSTRUCTIONS, SELFWIKI_INSTRUCTIONS

    cfg = tenant_config()
    return [
        DomainSpec(
            id="helpdesk",
            kind="workflow",
            hosted_agent_name=cfg.hosted_agent_name,
        ),
        DomainSpec(
            id="cockpit",
            kind="grounded",
            instructions=COCKPIT_INSTRUCTIONS,
            kb_name=cfg.cockpit_searchindex_knowledge_base,  # cockpit-si-kb (native searchIndex retrieve)
            ks_name=cfg.cockpit_searchindex_knowledge_source,  # cockpit-docbundles-si-ks
            search_index=cfg.cockpit_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            acl_group_map=cfg.acl_group_map,  # PARSED property (name→objectID), not the raw string
        ),
        DomainSpec(
            id="selfwiki",
            kind="grounded",
            instructions=SELFWIKI_INSTRUCTIONS,
            kb_name=cfg.selfwiki_searchindex_knowledge_base,  # selfwiki-si-kb (native searchIndex retrieve)
            ks_name=cfg.selfwiki_searchindex_knowledge_source,  # selfwiki-docbundles-si-ks
            search_index=cfg.selfwiki_search_index,  # direct-search fallback target (ACL trims here too)
            search_endpoint=cfg.azure_search_endpoint,
            # Single private audience = the app-users group (everyone with app access). Intentional
            # ACL (ADR/spec 2026-07-02): the self-wiki is stamped with this group; retrieval sends the
            # OBO header because this map is truthy. Empty APP_USERS_GROUP_ID → no map (dev/single-user).
            acl_group_map=({"app-users": cfg.app_users_group_id} if cfg.app_users_group_id else None),
        ),
        DomainSpec(id="platform", kind="tool"),
    ]


def _domain_deps(domain_id: str) -> list:
    """Auth deps, plus (shared mode only) the per-tenant entitlement gate. In self_hosted/
    dedicated this is exactly auth_dependencies() — byte-identical to today."""
    deps = auth_dependencies()
    if settings.deployment_mode == "shared":
        deps = [*deps, Depends(require_domain(domain_id))]
    return deps


def _mount_grounded(app: FastAPI, d: DomainSpec) -> None:
    """POST /{id} → stream the grounded archetype (cited Q&A). Captures current_user() in the
    endpoint body (the contextvar is lost inside the StreamingResponse generator)."""

    async def endpoint(request: Request) -> StreamingResponse:
        from app.core.auth import current_user
        from app.services.grounded import stream_grounded

        return StreamingResponse(
            stream_grounded(await request.json(), d, current_user()),
            media_type="text/event-stream",
        )

    app.add_api_route(
        f"/{d.id}",
        endpoint,
        methods=["POST"],
        dependencies=_domain_deps(d.id),
    )


def _mount_helpdesk(app: FastAPI, d: DomainSpec) -> None:
    """AG-UI workflow endpoint. With a KB wired, the per-request factory streams the Phase 2 steps
    + Phase 3 OBO/memory; without one, fall back to the single concierge agent."""
    from app.agents.concierge import _knowledge_configured, build_concierge_agent
    from app.workflow.graph import build_helpdesk_workflow
    from app.workflow.stream_fix import OrderedAgentFrameworkWorkflow

    if _knowledge_configured():
        add_agent_framework_fastapi_endpoint(
            app,
            agent=OrderedAgentFrameworkWorkflow(workflow_factory=build_helpdesk_workflow),
            path=f"/{d.id}",
            dependencies=_domain_deps(d.id),
        )
    else:
        add_agent_framework_fastapi_endpoint(
            app, agent=build_concierge_agent(), path=f"/{d.id}"
        )


def _mount_platform(app: FastAPI, d: DomainSpec) -> None:
    """Tool-driven ops concierge over the Microsoft first-party MCP servers. The platform_agent_proxy
    (a PerRequestAgent) rebuilds the agent on each run so tools are filtered under the caller's roles +
    OBO credential. Only mounted when platform is configured."""
    from app.agents.platform import platform_agent_proxy, platform_configured

    if platform_configured():
        add_agent_framework_fastapi_endpoint(
            app,
            agent=platform_agent_proxy,
            path=f"/{d.id}",
            dependencies=_domain_deps(d.id),
        )


def mount_domains(app: FastAPI) -> None:
    """One loop over `_domains()`, dispatching by `kind`. Registers the live per-domain endpoints
    on the app (the hosted twins stay in api/chat.py)."""
    for d in _domains():
        if d.kind == "grounded":
            _mount_grounded(app, d)
        elif d.kind == "workflow":
            _mount_helpdesk(app, d)
        elif d.kind == "tool":
            _mount_platform(app, d)
