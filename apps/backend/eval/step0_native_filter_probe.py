"""STEP 0 probe (unification gate) — does the NATIVE Foundry IQ retriever trim by a CALLER-SUPPLIED filter?

Throwaway verification SPIKE (NOT a product test, NOT red-green TDD). It answers ONE gate question that
decides how the next task is built:

  The agentic `knowledge_base_retrieve` MCP path does NOT honor the automatic per-user
  `x-ms-query-source-authorization` header (a known gap — azure-sdk-for-python#44454; only DIRECT
  /docs/search honors it). The NEW question: does the native retrieve API honor a caller-supplied group
  FILTER we pass explicitly — an OData filter over the stamped `groups` field — applied AT RETRIEVAL TIME?
  If YES → we get native-quality agentic retrieval + per-user ACL together. If NO → fall back to
  direct-search (Plan B).

MECHANISM UNDER TEST (discovered from Microsoft docs, RULE #1 — not invented):
  POST {search}/knowledgebases/{kb}/retrieve?api-version=2026-05-01-preview
  body.knowledgeSourceParams[].filterAddOn = "<OData filter>"   ← the caller filter
  (docs: learn.microsoft.com/azure/search/agentic-retrieval-how-to-retrieve — "Filter results by
   metadata"; filterAddOn is AND-combined with any persisted base filter, so it can only NARROW.)
  IMPORTANT constraint from the same docs: filterAddOn is documented for **search index knowledge sources
  ONLY**. Each knowledge source has a `kind` (searchIndex | azureBlob | …). The retrieve request must send
  the source's real kind (polymorphic discriminator), so the probe DISCOVERS the kind from the live KB def
  and only claims ✅ if the service ACCEPTS + ENFORCES filterAddOn for that kind.

The probe builds a per-user filter from the ACL group object-IDs (User A can read {confidential, internal,
public}, User B can read {public} only) as an OData `search.in` over the `groups` field, calls retrieve for
each user, and asserts the trim: A's references contain the confidential source, B's do NOT. It probes the
api-version independently (pinned 2026-05-01-preview first, then fallbacks) and _dump()s the exact request +
response (or the exact rejection error) so the next task is authored from captured fact.

Identity note: end users have NO Search RBAC, so the SERVICE credential on the retrieve call is the app/dev
identity (DefaultAzureCredential — Search Index Data Reader). The per-user distinction is carried entirely by
the CALLER FILTER we pass (the object-IDs the header path would derive from each user's token). We do NOT send
x-ms-query-source-authorization — the whole point is the filter, not the header.

Run (as a signed-in user, live infra):
    cd apps/backend && uv run python -m eval.step0_native_filter_probe
Skips cleanly (prints SKIP:, returns 0) when infra / test-user / ACL-group env is absent.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.request

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.settings import settings
from app.core.tenant import tenant_config

_SEARCH_SCOPE = "https://search.azure.com/.default"

# api-versions to probe, in order. The pinned one first (grounded._KB_API), then a newer preview + the GA.
# We DO NOT assume the pinned one accepts filterAddOn — RULE #1.
_API_CANDIDATES = ["2026-05-01-preview", "2025-11-01-preview", "2026-04-01"]

_PROBE_TEXT = "telemetria e observabilidade do cockpit"
_ASSISTANT_PROMPT = (
    "You retrieve grounding data about the Cockpit platform. Cite sources by their ref_id."
)


class _ProbeEnv(BaseSettings):
    """Reads the test-user + confidential-source fields from .env (pydantic doesn't export to os.environ,
    so a bare os.environ.get would falsely SKIP — the .env keys carry real values here)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    cockpit_test_user_a: str = ""
    cockpit_test_user_b: str = ""
    cockpit_test_password: str = ""
    cockpit_confidential_source: str = ""
    cockpit_acl_probe: str = ""


def _dump(label: str, obj: object) -> None:
    print(f"\n--- {label} ---")
    try:
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str)[:4000])
    except Exception:  # noqa: BLE001
        print(repr(obj)[:4000])


def _resolved_ids(names_or_ids: list[str]) -> list[str]:
    """Group NAMES → Entra object-IDs via the tenant ACL map; GUIDs pass through. Mirrors
    acl_setup._resolve — so a literal 'public' in default_groups doesn't leak into the filter as text."""
    gm = tenant_config().acl_group_map
    out: list[str] = []
    for n in names_or_ids:
        n = n.strip()
        if not n:
            continue
        out.append(gm.get(n, n))
    # dedup preserving order
    seen: set[str] = set()
    return [g for g in out if not (g in seen or seen.add(g))]


def _group_filter(group_ids: list[str]) -> str:
    """OData filter over the stamped `groups` field (Collection(Edm.String), filterable=True,
    permissionFilter=groupIds). `search.in(g, 'id1,id2', ',')` is the multi-value idiom for collections."""
    csv = ",".join(group_ids)
    return f"groups/any(g: search.in(g, '{csv}', ','))"


def _retrieve(
    search: str, kb: str, ks: str, kind: str, api: str, service_token: str,
    filter_add_on: str | None,
) -> tuple[int, dict]:
    """POST the native retrieve, optionally with a caller filterAddOn. Returns (http_status, body|error).
    `service_token` = app identity search-scoped bearer (Search Index Data Reader). `kind` is the source's
    real polymorphic discriminator (discovered live). filterAddOn omitted when None (baseline)."""
    url = f"{search}/knowledgebases/{kb}/retrieve?api-version={api}"
    ksp: dict = {"knowledgeSourceName": ks, "kind": kind}
    if filter_add_on is not None:
        ksp["filterAddOn"] = filter_add_on
    payload = {
        "messages": [
            {"role": "assistant", "content": [{"type": "text", "text": _ASSISTANT_PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": _PROBE_TEXT}]},
        ],
        "knowledgeSourceParams": [ksp],
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {service_token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:  # capture the exact server error verbatim
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return e.code, {"_raw": raw[:2000]}


def _sources_from_response(body: dict) -> list[str]:
    """Extract cited source identifiers. Two carriers (both harvested, deduped): references[].docKey /
    references[].sourceData.{title,blob_url,id}; and the extracted response[].content[].text (a JSON array
    of chunks with title/ref_id). Matched by SUBSTRING so a doc-key convention change doesn't break it."""
    out: list[str] = []
    for ref in body.get("references", []) or []:
        if ref.get("docKey"):
            out.append(str(ref["docKey"]))
        sd = ref.get("sourceData")
        if isinstance(sd, dict):
            for k in ("title", "blob_url", "id", "source"):
                if sd.get(k):
                    out.append(str(sd[k]))
    for msg in body.get("response", []) or []:
        for c in msg.get("content", []) or []:
            txt = c.get("text")
            if not txt:
                continue
            try:
                chunks = json.loads(txt)
            except Exception:  # noqa: BLE001
                out.append(str(txt))
                continue
            for ch in chunks if isinstance(chunks, list) else []:
                for k in ("title", "ref_id", "source", "blob_url"):
                    if isinstance(ch, dict) and ch.get(k):
                        out.append(str(ch[k]))
    seen: set[str] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


def _discover_source(search: str, kb: str, token: str) -> tuple[str, str, str] | None:
    """Live KB def → (knowledge_source_name, kind, api). The retrieve request keys off the SOURCE name
    and its real KIND (polymorphic discriminator) — never hardcode. RULE #1."""
    for api in _API_CANDIDATES:
        try:
            req = urllib.request.Request(
                f"{search}/knowledgebases/{kb}?api-version={api}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                kbdef = json.load(r)
        except Exception as exc:  # noqa: BLE001
            print(f"  KB-def discovery {api}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        srcs = kbdef.get("knowledgeSources", []) or []
        name = next((s.get("name") for s in srcs if s.get("name")), None)
        if not name:
            continue
        # The KB def entry may not carry the kind; fetch the knowledge source to read its discriminator.
        kind = srcs[0].get("kind") or _source_kind(search, name, token) or "searchIndex"
        return name, kind, api
    return None


def _source_kind(search: str, ks_name: str, token: str) -> str | None:
    for api in _API_CANDIDATES:
        try:
            req = urllib.request.Request(
                f"{search}/knowledgesources/{ks_name}?api-version={api}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return (json.load(r) or {}).get("kind")
        except Exception:  # noqa: BLE001
            continue
    return None


async def _run() -> int:  # noqa: C901 — one linear probe; readability over decomposition
    env = _ProbeEnv()
    cfg = tenant_config()
    tc = tenant_config()
    search = (cfg.azure_search_endpoint or "").rstrip("/")
    kb = cfg.cockpit_search_knowledge_base
    conf = env.cockpit_confidential_source
    conf_gid = tc.cockpit_acl_confidential_group
    pub_gid = tc.cockpit_acl_public_group
    internal_gid = tc.cockpit_acl_internal_group
    default_groups = [g for g in tc.cockpit_acl_default_groups.split(",") if g.strip()]

    if not (search and kb and conf and conf_gid and pub_gid):
        print("SKIP: native-filter probe needs live Search+KB, COCKPIT_CONFIDENTIAL_SOURCE and the ACL "
              "group IDs (confidential/public).")
        return 0

    if env.cockpit_acl_probe:
        global _PROBE_TEXT  # noqa: PLW0603 — allow the .env probe override, same idiom as the roundtrip test
        _PROBE_TEXT = env.cockpit_acl_probe

    # SERVICE credential = app/dev identity (Search Index Data Reader). End users have no search RBAC, so
    # the caller filter — not the user's token — carries the per-user distinction.
    from azure.identity import DefaultAzureCredential

    service_token = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token

    disc = _discover_source(search, kb, service_token)
    if not disc:
        print("SKIP: could not resolve the KB's knowledge source name/kind from the live KB def.")
        return 0
    ks_name, kind, disc_api = disc
    print(f"KB '{kb}' → source '{ks_name}' kind='{kind}' (discovered via api={disc_api})")

    # Per-user authorized group sets (resolved to object-IDs). Same object-IDs the header path derives.
    groups_a = _resolved_ids([conf_gid, internal_gid, pub_gid, *default_groups])
    groups_b = _resolved_ids([pub_gid, *default_groups])
    filter_a, filter_b = _group_filter(groups_a), _group_filter(groups_b)
    print(f"\nUser A authorized groups ({len(groups_a)}) → filterAddOn: {filter_a}")
    print(f"User B authorized groups ({len(groups_b)}) → filterAddOn: {filter_b}")
    print(f"confidential-source substring to trim on: '{conf}'\n")

    # Probe the api-version independently: which (if any) ACCEPTS filterAddOn for this source KIND?
    working_api: str | None = None
    last_err: dict = {}
    for api in _API_CANDIDATES:
        status, body = _retrieve(search, kb, ks_name, kind, api, service_token, filter_a)
        accepted = status in (200, 206)
        err = "" if accepted else json.dumps(body.get("error", body))[:500]
        print(f"api={api:20s} kind={kind:12s} status={status} accepted_filterAddOn={accepted} {err}")
        if accepted:
            working_api = api
            _dump(f"REQUEST that worked (api={api})", {
                "url": f"{search}/knowledgebases/{kb}/retrieve?api-version={api}",
                "knowledgeSourceParams": [
                    {"knowledgeSourceName": ks_name, "kind": kind, "filterAddOn": filter_a}],
            })
            _dump("RESPONSE.activity (shows the applied filter per subquery)", body.get("activity"))
            _dump("RESPONSE.references[0..3]", (body.get("references") or [])[:3])
            _dump("RESPONSE.response (extracted grounding)", body.get("response"))
            break
        last_err = body

    if not working_api:
        print("\n❌ VERDICT: no probed api-version ACCEPTED a caller filterAddOn for source kind "
              f"'{kind}'. The native retriever does NOT expose a caller filter on this KB → next task uses "
              "Plan B (direct-search over the index, per-user trim via x-ms-query-source-authorization).")
        _dump("Last rejection error (verbatim)", last_err.get("error", last_err))
        return 2

    # Filter accepted → run the two-user trim assertion (requires the ROPC users to build A/B queries;
    # but the filter itself already differs per user, so the app identity as service creds is sufficient).
    _, body_a = _retrieve(search, kb, ks_name, kind, working_api, service_token, filter_a)
    _, body_b = _retrieve(search, kb, ks_name, kind, working_api, service_token, filter_b)
    src_a = _sources_from_response(body_a)
    src_b = _sources_from_response(body_b)
    a_has = any(conf in s for s in src_a)
    b_has = any(conf in s for s in src_b)
    print(f"\nUser A filter ({len(src_a)} refs) contains confidential '{conf}': {a_has}")
    _dump("User A sources", src_a)
    print(f"User B filter ({len(src_b)} refs) contains confidential '{conf}': {b_has}")
    _dump("User B sources", src_b)

    if not a_has:
        print("\n⚠️  INCONCLUSIVE: A's broad filter did NOT surface the confidential source — the filter may "
              "over-restrict, the doc may not match the probe, or the stamp differs. Inspect the dumps.")
        return 3
    if b_has:
        print("\n❌ VERDICT: the caller filterAddOn is IGNORED — public-only User B's filter still returned "
              "the confidential source (LEAK) → next task uses Plan B (direct-search).")
        return 1

    print(f"\n✅ VERDICT: the NATIVE retriever TRIMS by a caller-supplied filter. filterAddOn='{filter_a}' "
          f"(OData over the stamped `groups` field) applied at retrieval time on api={working_api}, source "
          f"kind='{kind}': cleared A gets the confidential source, public-only B does not. → native agentic "
          "retrieval + per-user ACL together (no direct-search fallback needed).")
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
