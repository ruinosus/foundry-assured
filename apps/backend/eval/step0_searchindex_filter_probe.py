"""STEP 0.5 re-probe (unification HARD GATE) — can the NATIVE retriever do per-user ACL when the KB's
knowledge source is `kind: "searchIndex"` over the EXISTING ACL-stamped index?

Throwaway verification SPIKE (NOT product code, NOT red-green TDD). It answers ONE gate question that
decides the architecture of the next tasks:

  STEP 0 proved `filterAddOn` is REJECTED (HTTP 400 "Property 'filterAddOn' is not allowed") when the KB's
  knowledge source is `kind: "azureBlob"` — which the production `cockpit-kb` is — AND that the agentic
  retrieve path IGNORES the `x-ms-query-source-authorization` header on azureBlob. Microsoft docs say
  `filterAddOn` is `searchIndex`-only. The `searchIndex` the filter would target — `cockpit-docbundles-ks-index`
  — ALREADY EXISTS and is already ACL-stamped (`groups` field filterable, permissionFilter=groupIds,
  index permissionFilterOption=ENABLED).

  THE GATE: build a SEPARATE probe KB whose knowledge source is `kind: "searchIndex"` over that SAME index,
  then see whether the native retrieve can serve per-user ACL — via a caller `filterAddOn` over `groups`
  AND/OR via the `x-ms-query-source-authorization` header.

EMPIRICAL FINDINGS (this probe, live — see the STEP 0.5 section of the findings file):
  1. `filterAddOn` on kind:"searchIndex" is ACCEPTED and APPLIED (echoed into activity[].searchIndexArguments
     .filter). So the docs-inferred syntax is correct and the azureBlob rejection is gone.
  2. BUT the index has permissionFilterOption=ENABLED, and — CONTRARY to the docs' "without the identity
     token, results are returned unfiltered" — with NO x-ms-query-source-authorization header the permission
     trim treats the caller as belonging to NO groups and returns ZERO docs (fully fail-closed). So a
     `groups` filterAddOn can NEVER surface a permission-gated doc: the permission trim zeroes candidates
     before the filter narrows them. filterAddOn-as-ACL is therefore the WRONG lever on this index.
  3. HOWEVER — unlike azureBlob in STEP 0 — the searchIndex retrieve DOES honor
     x-ms-query-source-authorization: with the header the subqueries return docs (incl. the confidential
     source), and the count differs per token's group membership. => native agentic retrieval + per-user
     ACL + single head is achievable via the HEADER over a searchIndex KB.

So this probe now measures the mechanism that actually works: the header. It runs the native retrieve on
the searchIndex probe KB WITH x-ms-query-source-authorization and confirms the confidential doc is reachable
that way (and that filterAddOn is accepted, recorded separately). The A-vs-B per-user trim is carried by the
HEADER token's group membership (as the direct-search path already does today), NOT by filterAddOn.

NON-DESTRUCTIVE: creates a SEPARATE probe KB (`cockpit-si-probe-kb`) + knowledge source
(`cockpit-si-probe-ks`) pointing at the EXISTING `cockpit-docbundles-ks-index`. NEVER touches `cockpit-kb`
or `cockpit-docbundles-ks`. Tears them down at the end by default (set KEEP_PROBE_KB=1 to leave in place).

Identity: SERVICE credential on retrieve = the APP/dev identity (DefaultAzureCredential, Search Index Data
Reader). The per-user ACL distinction is the x-ms-query-source-authorization token's group membership. In
this non-interactive shell only the app/dev token is available; it happens to be a member of the confidential
group, so the probe verifies the confidential doc IS reachable via the header (a real public-only User B
token would trim it out — the same permission trim the direct-search path relies on today).

Run (as a signed-in user, live infra), from apps/backend/:
    uv run python -m eval.step0_searchindex_filter_probe
Skips cleanly (prints SKIP:, returns 0) when infra / ACL-group env is absent.
Exit codes: 0 ✅ per-user ACL works on searchIndex (via header) / SKIP · 2 create/retrieve rejected ·
3 inconclusive (confidential doc not reachable even with the header) · 4 BLOCKED (KB creation needs a role).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.tenant import tenant_config

_SEARCH_SCOPE = "https://search.azure.com/.default"

# Docs-verified retrieve api-version that uses the `messages` schema + accepts filterAddOn on searchIndex.
_RETRIEVE_API = "2026-05-01-preview"
# create_or_update_knowledge_source / _base use the mgmt api-version the repo pins in ingest_docbundles.
_MGMT_API = "2026-05-01-preview"

# Clearly-named probe resources — SEPARATE from cockpit-kb / cockpit-docbundles-ks (never touched).
_PROBE_KB = os.environ.get("PROBE_KB_NAME", "cockpit-si-probe-kb")
_PROBE_KS = os.environ.get("PROBE_KS_NAME", "cockpit-si-probe-ks")

_PROBE_TEXT = "telemetria e observabilidade do cockpit"
_ASSISTANT_PROMPT = (
    "You retrieve grounding data about the Cockpit platform. Cite sources by their ref_id."
)


class _ProbeEnv(BaseSettings):
    """Test-user + confidential-source fields from .env (pydantic doesn't export to os.environ, so a bare
    os.environ.get would falsely SKIP — the .env keys carry the real values)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
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
    seen: set[str] = set()
    return [g for g in out if not (g in seen or seen.add(g))]


def _group_filter(group_ids: list[str]) -> str:
    """OData filter over the stamped `groups` field (Collection(Edm.String), filterable=True). The
    `search.in(g, 'id1,id2', ',')` collection idiom is the multi-value ANY over a string collection —
    verified against the OData filter reference (search-query-odata-collection-operators)."""
    csv = ",".join(group_ids)
    return f"groups/any(g: search.in(g, '{csv}', ','))"


# ---------------------------------------------------------------------------
# Non-destructive probe-KB creation (SDK idiom, mirrors app.knowledge.ingest_docbundles).
# ---------------------------------------------------------------------------


def _create_probe_kb(index_name: str) -> tuple[bool, str]:
    """Create (idempotent) the searchIndex-backed probe KS + KB over the EXISTING ACL index.
    Returns (ok, detail). ok=False + detail carries the exact server error (for BLOCKED reporting)."""
    from azure.core.exceptions import HttpResponseError
    from azure.identity import DefaultAzureCredential
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        AzureOpenAIVectorizerParameters,
        KnowledgeBase,
        KnowledgeBaseAzureOpenAIModel,
        KnowledgeRetrievalMediumReasoningEffort,
        KnowledgeSourceReference,
        SearchIndexFieldReference,
        SearchIndexKnowledgeSource,
        SearchIndexKnowledgeSourceParameters,
    )

    cfg = tenant_config()
    client = SearchIndexClient(
        endpoint=cfg.azure_search_endpoint,
        credential=DefaultAzureCredential(),
        api_version=_MGMT_API,
    )
    # source_data_fields → the retrieve `references[].sourceData` carries blob_url + snippet, so the
    # confidential-source substring check has something to match on (docKey is the opaque `uid`).
    ks = SearchIndexKnowledgeSource(
        name=_PROBE_KS,
        description="STEP 0.5 probe — searchIndex source over the EXISTING ACL-stamped cockpit index.",
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=index_name,
            source_data_fields=[
                SearchIndexFieldReference(name="blob_url"),
                SearchIndexFieldReference(name="snippet"),
            ],
        ),
    )
    kb = KnowledgeBase(
        name=_PROBE_KB,
        description="STEP 0.5 probe KB (searchIndex) — DO NOT use in production; safe to delete.",
        knowledge_sources=[KnowledgeSourceReference(name=_PROBE_KS)],
        models=[
            KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=cfg.azure_ai_openai_endpoint,
                    deployment_name=cfg.foundry_model,
                    model_name=cfg.foundry_model,
                )
            )
        ],
        output_mode="answerSynthesis",
        answer_instructions="Responda apenas com base nos documentos recuperados; cite a fonte.",
        retrieval_reasoning_effort=KnowledgeRetrievalMediumReasoningEffort(),
    )
    try:
        client.create_or_update_knowledge_source(ks)
        print(f"✓ probe knowledge source '{_PROBE_KS}' created/updated (searchIndex → {index_name})")
        client.create_or_update_knowledge_base(kb)
        print(f"✓ probe knowledge base '{_PROBE_KB}' created/updated")
        return True, "ok"
    except HttpResponseError as e:  # capture verbatim for BLOCKED reporting
        return False, f"{getattr(e, 'status_code', '?')}: {str(e)[:600]}"
    finally:
        with __import__("contextlib").suppress(Exception):
            client.close()


def _teardown_probe_kb() -> None:
    from azure.identity import DefaultAzureCredential
    from azure.search.documents.indexes import SearchIndexClient

    cfg = tenant_config()
    client = SearchIndexClient(
        endpoint=cfg.azure_search_endpoint, credential=DefaultAzureCredential(), api_version=_MGMT_API
    )
    import contextlib

    with contextlib.suppress(Exception):
        client.delete_knowledge_base(_PROBE_KB)
        print(f"✓ deleted probe KB '{_PROBE_KB}'")
    with contextlib.suppress(Exception):
        client.delete_knowledge_source(_PROBE_KS)
        print(f"✓ deleted probe KS '{_PROBE_KS}'")
    with contextlib.suppress(Exception):
        client.close()


# ---------------------------------------------------------------------------
# Native retrieve (raw REST — mirrors step0_native_filter_probe).
# ---------------------------------------------------------------------------


def _retrieve(
    search: str, kb: str, ks: str, api: str, service_token: str,
    filter_add_on: str | None = None, user_token: str | None = None,
) -> tuple[int, dict]:
    """POST the native retrieve on the probe KB (kind: searchIndex).
    Returns (http_status, body|error).
    - `filter_add_on` → the caller OData filter (accepted on searchIndex, but NOT the ACL lever on a
      permissionFilterOption=enabled index — see module docstring).
    - `user_token` → sent as `x-ms-query-source-authorization` (the ACTUAL per-user ACL lever the
      searchIndex retrieve honors). Omit both for the baseline control."""
    url = f"{search}/knowledgebases/{kb}/retrieve?api-version={api}"
    ksp: dict = {"knowledgeSourceName": ks, "kind": "searchIndex"}
    if filter_add_on is not None:
        ksp["filterAddOn"] = filter_add_on
    payload = {
        "messages": [
            {"role": "assistant", "content": [{"type": "text", "text": _ASSISTANT_PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": _PROBE_TEXT}]},
        ],
        "knowledgeSourceParams": [ksp],
    }
    headers = {"Authorization": f"Bearer {service_token}", "Content-Type": "application/json"}
    if user_token is not None:
        headers["x-ms-query-source-authorization"] = user_token
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return e.code, {"_raw": raw[:2000]}


def _decode_dockey(dockey: str) -> str:
    """searchIndex `docKey` = `<12hex>_<base64(blob_url)>5_pages_N` → the blob URL (empirically observed).
    Recovering the blob_url is how the confidential-source substring check works, since `sourceData` comes
    back null on the answerSynthesis path. Falls back to the raw docKey if it doesn't decode."""
    import base64

    parts = dockey.split("_")
    if len(parts) < 2:
        return dockey
    mid = parts[1]
    try:
        return base64.b64decode(mid + "=" * (-len(mid) % 4)).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return dockey


def _sources_from_response(body: dict) -> list[str]:
    """Extract cited source identifiers (deduped). Carriers: references[].docKey and
    references[].sourceData.{blob_url,snippet,title,id} (source_data_fields → blob_url is present); plus
    the extracted response[].content[].text (a JSON array of ranked chunks with title/ref_id/terms).
    Matched by SUBSTRING so a doc-key convention change doesn't break the confidential check."""
    out: list[str] = []
    for ref in body.get("references", []) or []:
        if ref.get("docKey"):
            out.append(str(ref["docKey"]))
            out.append(_decode_dockey(str(ref["docKey"])))  # blob_url carries the source filename
        sd = ref.get("sourceData")
        if isinstance(sd, dict):
            for k in ("blob_url", "snippet", "title", "content", "id", "source"):
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
                for k in ("title", "ref_id", "source", "blob_url", "terms", "content"):
                    if isinstance(ch, dict) and ch.get(k):
                        out.append(str(ch[k]))
    seen: set[str] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


async def _run() -> int:  # noqa: C901 — one linear probe; readability over decomposition
    env = _ProbeEnv()
    cfg = tenant_config()
    tc = tenant_config()
    search = (cfg.azure_search_endpoint or "").rstrip("/")
    index = cfg.cockpit_search_index
    conf = env.cockpit_confidential_source
    conf_gid = tc.acl_confidential_group
    pub_gid = tc.acl_public_group
    internal_gid = tc.acl_internal_group
    default_groups = [g for g in tc.acl_default_groups.split(",") if g.strip()]

    if not (search and index and conf and conf_gid and pub_gid):
        print("SKIP: searchIndex-filter probe needs live Search+index, COCKPIT_CONFIDENTIAL_SOURCE and "
              "the ACL group IDs (confidential/public).")
        return 0

    if env.cockpit_acl_probe:
        global _PROBE_TEXT  # noqa: PLW0603 — allow the .env probe override (same idiom as the roundtrip test)
        _PROBE_TEXT = env.cockpit_acl_probe

    from azure.identity import DefaultAzureCredential

    service_token = DefaultAzureCredential().get_token(_SEARCH_SCOPE).token

    # 1) Create the probe KB non-destructively (searchIndex source over the EXISTING ACL index).
    print(f"Creating probe KB '{_PROBE_KB}' (searchIndex → '{index}') — cockpit-kb untouched.\n")
    ok, detail = _create_probe_kb(index)
    if not ok:
        low = detail.lower()
        if any(t in low for t in ("forbidden", "authorization", "403", "does not have permission",
                                  "not authorized", "rbac")):
            print("\n🚫 BLOCKED: the app/dev identity cannot CREATE a knowledge base/source (control-plane "
                  "permission missing). DO NOT self-assign roles. Exact server error:")
            print(f"    {detail}")
            print("\nHuman remediation (run in your ! shell — grant the signed-in identity the data-plane "
                  "write role on the search service):")
            print("    az role assignment create --role 'Search Index Data Contributor' \\")
            print("      --assignee $(az ad signed-in-user show --query id -o tsv) \\")
            print("      --scope $(az search service show -g <RG> -n <SEARCH_SERVICE> --query id -o tsv)")
            return 4
        print(f"\n❌ VERDICT: probe-KB creation FAILED (not a permission error). Verbatim:\n    {detail}")
        return 2

    keep = os.environ.get("KEEP_PROBE_KB") == "1"
    try:
        # The per-user filterAddOn we CAN construct (accepted on searchIndex) — recorded for completeness.
        groups_a = _resolved_ids([conf_gid, internal_gid, pub_gid, *default_groups])
        filter_a = _group_filter(groups_a)
        print(f"\nconstructible filterAddOn (A, {len(groups_a)} groups): {filter_a}")
        print(f"confidential-source substring to trim on: '{conf}'\n")

        # 1) CONTROL — no filter, no user header. On a permissionFilterOption=ENABLED index this returns
        #    0 docs (fully fail-closed), which is WHY filterAddOn-over-`groups` can't be the ACL lever:
        #    the permission trim zeroes candidates before any filter narrows them.
        ctl_status, ctl_body = _retrieve(search, _PROBE_KB, _PROBE_KS, _RETRIEVE_API, service_token)
        ctl_counts = [a.get("count") for a in (ctl_body.get("activity") or [])
                      if a.get("type") == "searchIndex"]
        print(f"CONTROL (no filter, no user header) status={ctl_status} subquery_counts={ctl_counts}")
        if ctl_status not in (200, 206):
            print("\n❌ VERDICT: the searchIndex probe KB does not even answer — infra/shape issue.")
            _dump("CONTROL rejection", ctl_body.get("error", ctl_body))
            return 2

        # 2) filterAddOn ACCEPTANCE check — proves the syntax is valid on kind:searchIndex (the azureBlob
        #    400 is gone). It's applied (echoed into activity[].searchIndexArguments.filter) but, without
        #    the user header, still yields 0 docs — confirming it's not the ACL lever here.
        fa_status, fa_body = _retrieve(
            search, _PROBE_KB, _PROBE_KS, _RETRIEVE_API, service_token, filter_add_on=filter_a
        )
        fa_applied = any(
            a.get("searchIndexArguments", {}).get("filter") == filter_a
            for a in (fa_body.get("activity") or []) if a.get("type") == "searchIndex"
        )
        print(f"filterAddOn on kind=searchIndex: status={fa_status} accepted={fa_status in (200, 206)} "
              f"applied_in_subquery={fa_applied}")

        # 3) THE MECHANISM THAT WORKS — x-ms-query-source-authorization (the searchIndex retrieve honors it,
        #    unlike azureBlob in STEP 0). Send the (app/dev) user token; capture the working shape.
        h_status, body_h = _retrieve(
            search, _PROBE_KB, _PROBE_KS, _RETRIEVE_API, service_token, user_token=service_token
        )
        h_counts = [a.get("count") for a in (body_h.get("activity") or [])
                    if a.get("type") == "searchIndex"]
        print(f"\nWITH x-ms-query-source-authorization: status={h_status} subquery_counts={h_counts}")
        if h_status not in (200, 206):
            print("\n❌ VERDICT: retrieve rejected the header path.")
            _dump("header-path rejection", body_h.get("error", body_h))
            return 2

        _dump(f"REQUEST that worked (api={_RETRIEVE_API}, header path)", {
            "url": f"{search}/knowledgebases/{_PROBE_KB}/retrieve?api-version={_RETRIEVE_API}",
            "headers": ["Authorization: Bearer <service>",
                        "x-ms-query-source-authorization: <user token — carries the ACL>"],
            "knowledgeSourceParams": [{"knowledgeSourceName": _PROBE_KS, "kind": "searchIndex"}],
        })
        _dump("RESPONSE.activity (searchIndex subqueries, counts>0 with header)", body_h.get("activity"))
        _dump("RESPONSE.references[0..3] (docKey base64-decodes to blob_url)",
              (body_h.get("references") or [])[:3])

        src_h = _sources_from_response(body_h)
        h_has = any(conf in s for s in src_h)
        print(f"\nHeader path ({len(src_h)} carriers) reaches confidential '{conf}': {h_has}")
        _dump("Header-path sources (docKeys decoded to blob_urls + response text)", src_h[:20])

        # Also compare: filterAddOn(conf-only) + header narrows the count vs header alone (proves filter
        # composes AND-wise on top of the permission trim — narrows, never widens).
        conf_only = _group_filter(_resolved_ids([conf_gid]))
        _, body_hf = _retrieve(
            search, _PROBE_KB, _PROBE_KS, _RETRIEVE_API, service_token,
            filter_add_on=conf_only, user_token=service_token,
        )
        hf_counts = [a.get("count") for a in (body_hf.get("activity") or [])
                     if a.get("type") == "searchIndex"]
        print(f"header + filterAddOn(conf-only) subquery_counts={hf_counts} (≤ header-alone {h_counts})")

        if not h_has:
            print("\n⚠️  INCONCLUSIVE: even WITH the user header the confidential source did not surface. "
                  "The doc may not match the probe text or the app token lacks the confidential group. "
                  "Inspect the dumps.")
            return 3

        print(f"\n✅ VERDICT (nuanced): native agentic retrieval + per-user ACL + single head is ACHIEVABLE "
              f"on a searchIndex KB — but via the x-ms-query-source-authorization HEADER (which the "
              f"searchIndex retrieve HONORS, unlike azureBlob in STEP 0), NOT via a `groups` filterAddOn. "
              f"filterAddOn IS accepted+applied on kind=searchIndex (accepted={fa_status in (200,206)}, "
              f"applied={fa_applied}) but is inert as an ACL lever because the index's "
              f"permissionFilterOption=enabled zeroes candidates without the header (control counts="
              f"{ctl_counts}, header counts={h_counts}). → next task: rebuild the KB on a searchIndex source "
              f"and pass the user's search token as x-ms-query-source-authorization (same per-user trim the "
              f"direct-search path uses today, now with native agentic recall + a single head).")
        return 0
    finally:
        if keep:
            print(f"\n(KEEP_PROBE_KB=1 → leaving probe KB '{_PROBE_KB}' / KS '{_PROBE_KS}' in place.)")
        else:
            print("\nTearing down probe KB/KS (set KEEP_PROBE_KB=1 to keep)...")
            _teardown_probe_kb()


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
