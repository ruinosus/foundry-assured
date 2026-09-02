---
type: architecture concept
title: Domain catalog, routing kinds, and frontend/backend parity
description: How the product defines assistant domains once in the backend catalog, mounts live endpoints by kind, and mirrors the same domain ids and kinds into the frontend registry and navigation surfaces.
tags: [architecture, domains, routing, frontend-backend-parity, tenancy]
verified:
  - by: openwiki/0.4.3
    at: 2026-09-02T18:24:34.393Z
sources:
  - id: openwiki-source-2c5d297c326a363e9ead1d50
    resource: repo://apps/backend/app/main.py
  - id: openwiki-source-ad23fff2cdc5e60751e74063
    resource: repo://apps/backend/app/modules/domains/internal/catalog.py
  - id: openwiki-source-dc60bf1c6d245f2fe0dd0051
    resource: repo://apps/backend/app/modules/domains/public.py
  - id: openwiki-source-961263732ea4068de79cda66
    resource: repo://apps/backend/app/modules/tenancy/public.py
  - id: openwiki-source-e87f49bb471a66fa69f1e61c
    resource: repo://apps/backend/app/registry.py
  - id: openwiki-source-0c199bd66a1c04098baf7d94
    resource: repo://apps/backend/tests/registry/domain_registry_test.py
  - id: openwiki-source-c9df086641842f127fabca5d
    resource: repo://apps/backend/tests/smoke/routes_snapshot_test.py
  - id: openwiki-source-d613209abb9617a94095aaea
    resource: repo://apps/backend/tests/smoke/routes_snapshot.json
  - id: openwiki-source-d71d85ad19f3d2709d16ba87
    resource: repo://apps/frontend/app/page.tsx
  - id: openwiki-source-74fbfd215197cf970d2d9546
    resource: repo://apps/frontend/components/console/DomainPicker.tsx
  - id: openwiki-source-8f3ec645f921d220f921d8cf
    resource: repo://apps/frontend/components/shell/AppShell.tsx
  - id: openwiki-source-0aa44e6a78708c32507b00fd
    resource: repo://apps/frontend/components/shell/ChatDock.tsx
  - id: openwiki-source-61b88fa07789f6d2b2c9d850
    resource: repo://apps/frontend/lib/domains.ts
generated: { by: "openwiki/0.4.3", at: "2026-09-02T18:24:34.393Z" }
---

The product treats “which assistant domains exist” as shared product data, not as composition-root trivia. On the backend, `app.modules.domains.public` is the public seam that exports the static topology (`DOMAIN_KINDS`) plus the per-request configured specs (`domain_spec` and `domain_specs`), and both composition roots consume that seam instead of re-declaring domain lists locally.[`apps/backend/app/modules/domains/public.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/public.py#L1-L18) [`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L1-L23)

## What the backend catalog owns

`DomainSpec` is the backend’s row shape for configured domains. It carries the domain id, kind, retrieval configuration, document access policy, and optional hosted twin name. The class enforces two fail-fast invariants that matter to routing and retrieval:

- a `grounded` domain must declare either `kb_name` or `search_index`
- any domain that keeps the default `document_access="acl"` must also declare `search_index`

Those checks make bad catalog entries fail when the registry is built instead of later on a live request.[`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L33-L79)

The catalog is deliberately split into two layers:

- `DOMAIN_KINDS` is the static topology: which domain ids exist and which runtime kind each uses
- `domain_specs()` resolves the configured subset against the current request tenant

That split is what lets the app boot in shared mode. Mounting can safely read the static topology at startup, while request handlers resolve tenant-sensitive config lazily only after tenancy has identified the caller.[`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L81-L128) [`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L250-L270)

Today `DOMAIN_KINDS` contains seven mountable backend domains:

- `helpdesk` as `workflow`
- `techdocs` and `selfwiki` as `grounded`
- `platform` and `builder` as `tool`
- `oncall` and `deepcall` as `graph`

But only four of those appear in `domain_specs()`: `helpdesk`, `techdocs`, `selfwiki`, and `platform`. That is intentional. `domain_specs()` is the configured, tenant-resolved subset used for retrieval-heavy domains, while `DOMAIN_KINDS` is the full mountable topology used by routing and parity checks.[`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L90-L107) [`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L122-L206)

## How routing dispatches by kind

`app/registry.py` owns composition only: mounting endpoints and including routers. `mount_domains(app)` walks `DOMAIN_KINDS` once and dispatches by `kind`:

- `grounded` → `_mount_grounded`
- `workflow` → `_mount_helpdesk`
- `tool` → `_mount_builder` or `_mount_platform`, selected by domain id
- `graph` → `_mount_graph`

After the loop it also mounts `/flow`, which is a workflow runtime surface rather than a catalog domain.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L250-L270)

### Grounded domains

Grounded domains register `POST /{domain_id}` with `app.add_api_route`. The mounted handler resolves `domain_spec(domain_id)` inside the request, not at boot, so shared-mode tenants do not leak a first-resolved tenant’s knowledge base or ACL config to everyone else. The handler then streams `stream_grounded(...)` and passes the caller’s preferred language from `Accept-Language` when present.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L46-L91)

### Workflow domains

`helpdesk` is mounted as an AG-UI workflow endpoint. When knowledge is configured, the route uses a per-request workflow factory that closes over `domain_id` and resolves `domain_spec(domain_id)` only when the request runs. Without knowledge configured, the route falls back to the concierge agent. This preserves the same lazy-resolution rule as grounded domains: no tenant config is read during startup.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L103-L135)

### Tool domains

The `tool` kind currently covers two different surfaces behind the same routing kind:

- `builder` mounts the wizard assistant proxy
- `platform` mounts the platform agent proxy, but only when platform configuration is available

The dispatch is still centralized in `mount_domains`; it just branches by id within the `tool` kind because the two agents are not built the same way.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L168-L198) [`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L257-L267)

### Graph domains

`graph` domains are the LangGraph-style branch. `_mount_graph` chooses either `deepcall` or `oncall`, verifies that the selected graph is configured, registers the AG-UI endpoint through LangGraph’s adapter on an `APIRouter`, then includes that router on the app with the shared domain dependencies applied. That router indirection is a security invariant: the upstream LangGraph adapter does not accept `dependencies=`, so registering directly on the app would leave those domain endpoints without auth or shared-mode entitlement checks.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L200-L247)

## Domain dependencies and tenancy gates

There are two layers of “domain dependencies”, and the distinction matters when adding or changing routes.

At the tenancy seam, `app.modules.tenancy.public.domain_deps(domain_id)` is the canonical gate for a domain endpoint. It always includes `auth_dependencies()`, and in `shared` deployment mode it appends `Depends(require_domain(domain_id))` so the route is only reachable when the tenant is entitled to that domain. In `self_hosted` and `dedicated`, it stays byte-identical to plain auth dependencies.[`apps/backend/app/modules/tenancy/public.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/tenancy/public.py#L113-L124)

At the composition seam, `app.registry.domain_deps(domain_id)` wraps tenancy’s gate and appends the conversation binding dependency from the conversations module. `mount_domains()` uses this composed dependency list for every mounted domain kind, so conversation binding and usage instrumentation stay uniform across runtimes instead of depending on each individual domain mount to remember them.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L94-L100)

Tenancy itself is installed before requests start, and the composition root also hands tenancy the valid server catalog ids at boot through `set_server_catalog(...)`. That keeps tenancy’s validation dependent on composition-provided platform data instead of importing the platform registry itself.[`apps/backend/app/main.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/main.py#L78-L105)

## Frontend mirror of the domain catalog

The frontend keeps its own registry in `apps/frontend/lib/domains.ts`, but it is intentionally the mirror of the backend topology, not an independent invention. Each frontend `Domain` entry carries the stable `id`, `kind`, `endpoint`, `framework`, icon, optional hosted twin id, and surface classification. Comments in the file explicitly define it as the single source of truth for frontend agent selection, sidebar navigation, generic `/d/[domain]` console routing, landing-page cards, and starter prompts.[`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L1-L16) [`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L24-L41)

The current frontend registry mirrors the backend ids and kinds:

- `builder` as `tool`, but marked `surface: "dock"`
- `helpdesk` as `workflow`
- `techdocs` and `selfwiki` as `grounded`
- `oncall` and `deepcall` as `graph`
- `platform` as `tool`

`CHAT_DOMAINS` then filters `DOMAINS` down to entries whose surface is `domain`, excluding `builder` from the main assistant selector and landing-page cards while still keeping it available to the dock and runtime registry.[`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L43-L118)

## Where frontend parity shows up in the UI

The frontend registry is consumed in multiple navigation surfaces, which is why parity failures are product-visible quickly.

- `AppShell` uses `CHAT_DOMAINS[0].id` to create the sidebar’s “assistants” entry and uses `DOMAINS.find(...)` to derive the current domain title for `/d/<id>` routes.[`apps/frontend/components/shell/AppShell.tsx`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/components/shell/AppShell.tsx#L34-L52) [`apps/frontend/components/shell/AppShell.tsx`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/components/shell/AppShell.tsx#L238-L249)
- `DomainPicker` groups `CHAT_DOMAINS` by `framework`, using `FRAMEWORK_ORDER` to present the assistant selector grouped by runtime family rather than a flat list.[`apps/frontend/components/console/DomainPicker.tsx`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/components/console/DomainPicker.tsx#L16-L18) [`apps/frontend/components/console/DomainPicker.tsx`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/components/console/DomainPicker.tsx#L62-L96)
- The public landing page uses `CHAT_DOMAINS[0].id` for its primary “open chat” CTA and maps `CHAT_DOMAINS` into the role-card grid.[`apps/frontend/app/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/app/page.tsx#L23-L53)
- `ChatDock` uses the full `DOMAINS` list for its agent selector, which is why `builder` can stay available as a dock-only assistant without appearing in the main console selector.[`apps/frontend/components/shell/ChatDock.tsx`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/components/shell/ChatDock.tsx#L17-L27) [`apps/frontend/components/shell/ChatDock.tsx`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/components/shell/ChatDock.tsx#L56-L78)

## Parity invariants between backend and frontend

The important invariant is not “both sides have a list”; it is “the backend mountable topology and the frontend registry must agree on domain ids and kinds.” Backend tests enforce that by reading `apps/frontend/lib/domains.ts` from disk, stripping comments, extracting `{id, kind}` pairs, and comparing them to `DOMAIN_KINDS`. The test names missing backend-only domains, missing frontend-only domains, and kind mismatches before failing.[`apps/backend/tests/registry/domain_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/registry/domain_registry_test.py#L85-L115) [`apps/backend/tests/registry/domain_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/registry/domain_registry_test.py#L125-L145)

A second invariant is that route-surface changes are intentional and reviewed. `routes_snapshot_test.py` captures the live HTTP method+path surface under three deployment profiles and compares it to `routes_snapshot.json`, so adding or removing a mounted domain route changes the snapshot diff. The snapshot exists specifically to catch composition refactors that still boot but silently lose or gain routes.[`apps/backend/tests/smoke/routes_snapshot_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/smoke/routes_snapshot_test.py#L1-L18) [`apps/backend/tests/smoke/routes_snapshot_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/smoke/routes_snapshot_test.py#L30-L85)

The current snapshot fixture shows the mounted domain endpoints in the recorded route surface, including `/helpdesk`, `/techdocs`, `/selfwiki`, `/platform`, `/builder`, `/flow`, and the graph routes when the relevant profile is enabled.[`apps/backend/tests/smoke/routes_snapshot.json`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/smoke/routes_snapshot.json#L296-L390)

## Adding a new domain safely

To add a new domain without breaking frontend/backend parity, keep the following extension points and invariants together:

1. Add the backend topology entry in `DOMAIN_KINDS` with the correct `kind`.[`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L90-L107)
2. If the domain needs tenant-resolved retrieval config, add its `DomainSpec` row to `domain_specs()`, making sure the `DomainSpec` invariants still hold.[`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L122-L206)
3. Ensure `mount_domains()` already knows how to mount that `kind`; if it is a genuinely new kind, add a new branch there. If it reuses an existing kind but needs id-specific behavior like `builder` versus `platform`, extend the kind branch carefully.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L250-L270)
4. Make sure the mounted route uses `registry.domain_deps(domain_id)` so auth, shared-mode entitlement, and conversation binding stay uniform.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L94-L100)
5. Mirror the same `id`, `kind`, and endpoint in `apps/frontend/lib/domains.ts`, and decide whether it belongs on the `domain` surface or only the `dock` surface.[`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L24-L41) [`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L43-L118)
6. Run the backend parity and snapshot tests. `domain_registry_test` catches id/kind drift against the frontend file, and `routes_snapshot_test` catches route-surface drift against the frozen baseline.[`apps/backend/tests/registry/domain_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/registry/domain_registry_test.py#L117-L145) [`apps/backend/tests/smoke/routes_snapshot_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/smoke/routes_snapshot_test.py#L48-L85)

## Failure modes this design is preventing

This arrangement exists to prevent a few specific classes of breakage:

- **Boot-time tenant reads in shared mode.** Mounting reads `DOMAIN_KINDS`, not `domain_specs()`, so startup does not require a resolved tenant.[`apps/backend/app/modules/domains/internal/catalog.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/domains/internal/catalog.py#L81-L89) [`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L250-L256)
- **A frontend-only or backend-only domain.** `domain_registry_test` compares backend topology directly against the frontend registry file on disk.[`apps/backend/tests/registry/domain_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/registry/domain_registry_test.py#L96-L145)
- **A domain route mounted without auth or entitlement.** Tenancy owns the canonical domain gate, and the graph branch uses `APIRouter` inclusion specifically because its adapter cannot accept dependencies directly.[`apps/backend/app/modules/tenancy/public.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/tenancy/public.py#L1-L10) [`apps/backend/app/modules/tenancy/public.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/modules/tenancy/public.py#L113-L124) [`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L229-L247)
- **A refactor that silently changes the HTTP surface.** The smoke snapshot freezes routes by deployment profile and forces intended changes to be reviewed as fixture diffs.[`apps/backend/tests/smoke/routes_snapshot_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/smoke/routes_snapshot_test.py#L1-L18) [`apps/backend/tests/smoke/routes_snapshot_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/smoke/routes_snapshot_test.py#L65-L85)
