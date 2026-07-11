# Prototype — per-tenant prompt/persona overlays (DNA)

> **PROTOTYPE / spike.** For the owner to *evaluate the value* before deciding to
> productize. It changes **no production behavior** and is not meant to be merged
> as-is. SDLC: story `proto-tenant-overlays` under feature `f-dna-adoption`
> (scope `foundry-dev`).

## What this proves

A foundry (multitenant SaaS) can ship **one** agent and let **each customer
customize its persona/tone** with a small overlay file — while the shared base
stays intact. No fork of the agent, no redeploy, no per-customer code branch.

Concretely: the helpdesk **concierge** agent has a shared `Soul` (persona). Tenant
`acme` ships a Soul overlay that gives the concierge ACME's white-glove brand
voice. Composed for `tenant=acme` you get ACME's persona; composed with no
tenant you get the original platform persona — byte-for-byte unchanged. The
grounded-answer delta and the citation guardrail are shared by both, never
duplicated.

Run it:

```bash
.venv-dna/bin/python demo/tenant_overlays_demo.py
```

Real captured output (`demo/_captured_output.txt`), abridged:

```
### (a) BASE — no tenant (shared platform persona)
You are the Helpdesk Concierge, an internal engineering support assistant. ...

### (b) TENANT = acme — overlay composed on top of the SAME base
You are **Acme Concierge**, ACME Corp's white-glove engineering support assistant. ...

ASSERTIONS
  persona changed for acme .......... True
  shared body (delta+guardrail) kept  True
RESULT: PASS — per-tenant override proven, base untouched
```

Visual, side-by-side for the owner: **`demo/tenant_overlays.html`**.

## The DNA tenancy API used

DNA models **Tenant as a first-class kernel dimension, orthogonal to layers**
(same maxim as the upstream SDK). Two moving parts:

1. **Bind a tenant to the kernel.** `Kernel(tenant="acme")` — or
   `kernel.with_tenant("acme")`. The kernel threads that tenant into every
   read/compose call. (`Kernel.quick(scope)` is the tenant-*blind* fast path, so
   the demo builds the full filesystem kernel and passes the tenant in — see
   `_kernel()` in the demo.)

2. **Compose as usual.** `kernel.instance(scope).build_prompt(agent)`. Because
   the kernel carries the tenant, the `FilesystemSource` **unions the tenant
   overlay over the platform base**, with the overlay *shadowing* base docs by
   `kind + name` (`merge_override` semantics). Nothing about the `build_prompt`
   call changes — tenancy is transparent to the composition surface.

**On-disk overlay convention** (the whole contract):

```
# base — shipped once, owned by the platform
apps/backend/.dna/helpdesk/souls/concierge/SOUL.md

# overlay — the ONLY file a tenant writes
apps/backend/.dna/tenants/acme/scopes/helpdesk/souls/concierge/SOUL.md
```

Same `kind` (Soul) + same `name` (`concierge`) at the tenant path → it shadows
the base for that tenant only. A second tenant is a second folder; the base
agent, guardrail and eval-cases are never copied.

Files added by this prototype (all new, all additive):

- `apps/backend/.dna/tenants/acme/scopes/helpdesk/souls/concierge/SOUL.md` — ACME persona
- `apps/backend/.dna/tenants/acme/scopes/helpdesk/souls/concierge/soul.json` — overlay Soul manifest
- `demo/tenant_overlays_demo.py` — runnable proof
- `demo/tenant_overlays.html` — owner-facing visual
- `demo/_captured_output.txt` — real run output

## What productizing would cost in the foundry

The backend is already multitenant, so the mechanism is *reused*, not built:

1. **Thread the request's tenant into composition.** Wherever the runtime builds
   the concierge prompt today, replace the tenant-blind kernel with one bound to
   the authenticated tenant: `Kernel(tenant=request.tenant)` (or `with_tenant`).
   This is the single load-bearing wiring change. In `apps/backend`, that is the
   place that instantiates the kernel / calls `build_prompt` for the concierge.

2. **Give tenants a place to write overlays.** For self-service, the source
   should be **Postgres** (not filesystem) so overlays are per-tenant rows
   written through `kernel.write_document(..., tenant="acme")` — same overlay
   semantics, no disk. The FS layout in this prototype is the dev-time mirror of
   those rows.

3. **Author surface.** A minimal "Customize your assistant" form that PUTs a
   Soul overlay for the caller's tenant. The kernel already validates and
   invalidates cache on write; the UI is the only new build.

4. **Guardrails on what a tenant may override.** Decide the overridable set
   (persona/tone: yes; the citation guardrail: probably locked). DNA supports
   this via which Kinds are declared tenant-overlayable.

Rough shape: **wiring (1) is hours**, the rest is the product surface (author UI
+ overridability policy), not kernel work.

## Honest gaps / gotchas

- **`Kernel.quick` is tenant-blind.** The convenient one-liner doesn't take a
  tenant, so tenant composition needs the full kernel build (done in the demo).
  A `Kernel.quick(scope, tenant=...)` convenience would remove this footgun —
  filed as a kaizen against DNA (adoption → evolution loop).
- **Filesystem source is dev-only for this.** Real multitenant self-service
  wants the Postgres source so overlays are rows, not files on a deploy image.
  The prototype uses FS because it's the zero-infra way to *show the value*.
- **Overridability policy is out of scope here.** This prototype overrides the
  whole persona (the Soul). A production version must decide, per Kind, what a
  tenant may and may not change (e.g. lock safety guardrails).
- **Field-level vs whole-doc override.** This demo shadows the whole Soul doc.
  DNA also exposes `merge_field_level` for finer deltas; not needed to prove the
  value, but relevant when tenants should tweak *part* of a persona.
