#!/usr/bin/env python3
"""
DNA per-tenant prompt/persona overlay — PROTOTYPE (spike).

Proves the foundry killer-feature: ONE shared agent (the helpdesk `concierge`),
customized PER TENANT via a Soul overlay — the base stays intact, no fork, no
redeploy. A tenant ships a YAML/Markdown overlay under
`tenants/<tenant>/scopes/<scope>/…` and the kernel composes it on top of the
shared base at read time.

Tenancy API used (all real DNA SDK 0.5):
  * `Kernel(tenant="acme")` — Tenant is a first-class kernel dimension,
    orthogonal to layers.
  * `k.instance(scope).build_prompt(agent)` — composes the prompt; when the
    kernel carries a tenant, the FilesystemSource unions the tenant overlay
    over the platform base (overlay shadows base by kind+name).
  * On-disk overlay convention (FilesystemSource):
        base    : <base_dir>/<scope>/souls/concierge/SOUL.md
        overlay : <base_dir>/tenants/<tenant>/scopes/<scope>/souls/concierge/SOUL.md

Run:
    .venv-dna/bin/python demo/tenant_overlays_demo.py
"""
from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path

from dna import Kernel
from dna.adapters.filesystem import FilesystemCache, FilesystemSource
from dna.adapters.resolvers import LocalResolver
from dna.kernel.kernel_bootstrap import EXTENSIONS_ENTRY_POINT_GROUP

# The helpdesk scope lives under apps/backend/.dna
REPO = Path(__file__).resolve().parent.parent
BASE_DIR = str(REPO / "apps" / "backend" / ".dna")
SCOPE = "helpdesk"
AGENT = "concierge-grounded"


def _kernel(tenant: str | None) -> Kernel:
    """A filesystem kernel with every extension loaded, optionally tenant-bound.

    This mirrors `Kernel.quick` (which is tenant-blind) but threads the tenant
    into the kernel constructor so composition resolves the per-tenant overlay.
    """
    k = Kernel(tenant=tenant)
    k.source(FilesystemSource(BASE_DIR))
    k.cache(FilesystemCache(BASE_DIR))
    k.resolver("local", LocalResolver(base_dir=BASE_DIR))
    for ep in importlib.metadata.entry_points(group=EXTENSIONS_ENTRY_POINT_GROUP):
        try:
            k.load(ep.load()())
        except Exception:  # noqa: BLE001 — fail-soft on a broken extension
            pass
    return k


def build_prompt(tenant: str | None) -> str:
    return _kernel(tenant).instance(SCOPE).build_prompt(AGENT)


def main() -> int:
    base = build_prompt(tenant=None)
    acme = build_prompt(tenant="acme")

    bar = "=" * 78
    print(bar)
    print(f"AGENT: {AGENT}   SCOPE: {SCOPE}   BASE_DIR: {BASE_DIR}")
    print(bar)

    print("\n### (a) BASE — no tenant (shared platform persona)\n")
    print(base)

    print("\n" + bar)
    print("\n### (b) TENANT = acme — overlay composed on top of the SAME base\n")
    print(acme)

    print("\n" + bar)
    # Prove the value: persona differs, base intact.
    base_persona = base.splitlines()[0]
    acme_persona = acme.splitlines()[0]
    persona_changed = base_persona != acme_persona
    # The grounded delta + guardrail (everything after the persona line) is shared.
    base_body = "\n".join(base.splitlines()[1:]).strip()
    acme_body = "\n".join(acme.splitlines()[1:]).strip()
    body_shared = base_body == acme_body

    print("ASSERTIONS")
    print(f"  persona changed for acme .......... {persona_changed}")
    print(f"  shared body (delta+guardrail) kept  {body_shared}")
    print(f"  base persona: {base_persona[:70]}…")
    print(f"  acme persona: {acme_persona[:70]}…")

    ok = persona_changed and body_shared
    print(f"\nRESULT: {'PASS — per-tenant override proven, base untouched' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
