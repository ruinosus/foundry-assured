"""The single retrieval seam — `retrieve()` — that every grounded domain uses.

One interface, two identities, two engines behind the same seam:

- **PRIMARY (native agentic retrieve):** when the domain has a `kb_name`, POST the Foundry IQ KB
  `retrieve` endpoint over a **searchIndex**-backed KB. Per-user ACL rides the
  `x-ms-query-source-authorization` header (the searchIndex retrieve HONORS it — verified live in the
  STEP 0.5 findings; the old #44454 "agentic ignores ACL" gap was blob-specific). Service auth on the
  call is the APP managed identity (Search Index Data Reader); the header carries the END USER's
  search-scoped token, and its group membership drives the permission trim on the ACL-stamped index.

- **FALLBACK (direct-search-as-user):** when the domain has no `kb_name`, `_direct_search_authorized`
  (defined below) does a DIRECT search over `domain.search_index` with the same header trim. This is the
  fallback engine — it lives HERE now (moved out of grounded.py, which collapsed to one archetype).

Two token identities (mirrors grounded.py:216–224):
  - service credential on the retrieve call = APP managed identity (end users have no Search RBAC);
  - the per-user distinction = the `x-ms-query-source-authorization` header (user's OBO search token),
    attached ONLY on ACL domains (public domains omit it → the model runs as the app identity).

Fail-closed (RULE #6): an ACL domain whose user token is None sends no header; on a
permissionFilterOption=enabled index the retrieve then belongs to no groups and returns ZERO docs — the
correct fail-closed behavior, never a leak.

The native request shape is COPIED from the proven probe
`apps/backend/eval/step0_searchindex_filter_probe.py` (RULE #1 — captured fact, not invented). The
`docKey` → blob_url decode was VERIFIED LIVE against 38 real `cockpit-si-kb` docKeys (see `_decode_dockey`
and `eval/dockey_decode_test.py`) — the probe's naïve `split("_")[1]` decode fell back to raw base64 for
~half the keys; the current decode strips the prefix/`_pages_` suffix by regex and uses standard base64. The
per-citation `snippet` is read from `references[].sourceData.snippet`, populated by
`includeReferenceSourceData=true` on the ksp — VERIFIED LIVE against `cockpit-si-kb` (every reference came
back with a non-empty snippet, ACL trim intact; see `_native_retrieve`, `_sourcedata_snippet`, and
`eval/native_snippet_test.py`). This REPLACES the old `references[].id` ↔ `response`-chunk `ref_id` join,
which never fired on the `answerSynthesis` KB (there `response` is the prose answer, not a chunk array).
"""

from __future__ import annotations

import base64
import re

from app.core.settings import settings

_SEARCH_SCOPE = "https://search.azure.com/.default"
_KB_API = "2026-05-01-preview"  # verified in STEP 0.5 (the `messages`-schema retrieve)


async def retrieve(query: str, user, domain, *, top: int = 8) -> list[dict]:
    """Retrieve authorized grounding docs for `query`, as `[{index, source, url, snippet}]`.

    `domain` is DUCK-TYPED (DomainSpec doesn't exist yet): reads `.kb_name` (→ native path),
    `.search_endpoint`, `.search_index` (→ fallback path) via plain attribute access.

    `user` is the signed-in User captured in the endpoint (the current_user() contextvar is lost inside
    streaming generators — see grounded._async_credential). None → app identity (dev / no-auth / public).

    `top` is honored only on the FALLBACK direct-search path; the native KB retrieve has no proven
    result-count param, so it returns the KB's default result set (see _native_retrieve, RULE #1).
    """
    from azure.identity.aio import DefaultAzureCredential as _AppCredential

    app_cred = _AppCredential()
    try:
        primary = (await app_cred.get_token(_SEARCH_SCOPE)).token  # app MI (service credential)
        # The per-user ACL header is attached ONLY on ACL'd domains (truthy acl_group_map) — RULE #6.
        # A genuinely public domain (no acl_group_map) omits it and runs as the app identity; an ACL'd
        # domain sends the user's OBO token so the index trims to what the user may read.
        user_token = await _user_search_token(user) if getattr(domain, "acl_group_map", None) else None
        if getattr(domain, "kb_name", None):  # PRIMARY: native agentic retrieve
            rows = await _native_retrieve(domain, query, primary, user_token)
        else:  # FALLBACK: direct-search-as-user (the engine lives here now)
            rows = await _direct_search_authorized(domain, query, primary, user_token, top=top)
        return _project(rows)
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await app_cred.close()


async def _user_search_token(user) -> str | None:
    """The END USER's search-scoped token via OBO — or None when auth is off / no user (dev / public).

    Mirrors grounded._async_credential: no user identity → None (the caller then omits the ACL header;
    public domains run as the app identity). Returns a raw token string, not a credential."""
    if not settings.auth_enabled or user is None:
        return None
    from azure.identity.aio import OnBehalfOfCredential

    cred = OnBehalfOfCredential(
        tenant_id=settings.entra_tenant_id,
        client_id=settings.entra_api_client_id,
        client_secret=settings.entra_api_client_secret,
        user_assertion=user.access_token,
    )
    try:
        return (await cred.get_token(_SEARCH_SCOPE)).token
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            await cred.close()


async def _native_retrieve(
    domain, query: str, primary: str, user_token: str | None
) -> list[dict]:
    """Native Foundry IQ KB retrieve over a searchIndex-backed KB (the PRIMARY path).

    Request + parse COPIED from step0_searchindex_filter_probe.py (RULE #1):
      POST {search}/knowledgebases/{kb}/retrieve?api-version=2026-05-01-preview
      body.messages = [assistant prompt, user query]; knowledgeSourceParams[].kind = "searchIndex".
      Service auth = app MI bearer; x-ms-query-source-authorization = user token (ACL) ONLY when present.

    No `top` knob: the probe never sent a result-count param on the KB retrieve, so (RULE #1) this path
    returns the KB's DEFAULT result set rather than inventing a request field. Only the direct-search
    fallback honors `top`.

    Returns raw rows [{source, url, snippet}] (dedup + 1-based reindex happen centrally in _project)."""
    import httpx

    search = domain.search_endpoint.rstrip("/")
    kb = domain.kb_name
    # The KB's knowledge source name. The probe used a separate probe KS; production duck-typing exposes
    # it as `.ks_name` when the KB has a differently-named source, else the KB name is the safe default.
    ks = getattr(domain, "ks_name", None) or kb

    url = f"{search}/knowledgebases/{kb}/retrieve?api-version={_KB_API}"
    # includeReferenceSourceData=true → each references[] entry carries its own sourceData
    # ({uid, blob_url, snippet}) populated from the KS's source_data_fields. VERIFIED LIVE against
    # `cockpit-si-kb` (eval/native_snippet_test.py fixture): 39/39 (User A) and 37/37 (User B) references
    # came back with a non-empty `snippet`, and the per-user ACL trim held (A reaches the confidential
    # doc, B does not). This is the single-call source of the per-citation snippet — the old
    # response[].ref_id join never fired because this KB runs `answerSynthesis`, so `response` is the
    # prose answer (not a JSON chunk array) and, without this flag, `sourceData` came back null.
    ksp: dict = {
        "knowledgeSourceName": ks,
        "kind": "searchIndex",
        "includeReferenceSourceData": True,
    }
    payload = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": getattr(domain, "instructions", None)
                        or "Retrieve grounding data and cite sources by their ref_id.",
                    }
                ],
            },
            {"role": "user", "content": [{"type": "text", "text": query}]},
        ],
        "knowledgeSourceParams": [ksp],
    }
    headers = {"Authorization": f"Bearer {primary}", "Content-Type": "application/json"}
    if user_token is not None:  # ACL domains only; public domains omit the header (RULE #6 fail-closed)
        # BARE user token — no "Bearer " prefix (RULE #1: copy the PROVEN shape, not the prose). Both the
        # probe that empirically proved the searchIndex ACL trim (step0_searchindex_filter_probe.py:241)
        # and the direct-search fallback (_direct_search_authorized, below) send it bare.
        headers["x-ms-query-source-authorization"] = user_token

    async with httpx.AsyncClient(timeout=120) as http:
        resp = await http.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()

    return _parse_native(body)


_DOCKEY_HEX_PREFIX = re.compile(r"^[0-9a-fA-F]{12}_")
_DOCKEY_PAGES_SUFFIX = re.compile(r"_pages_\d+$")
_BLOB_URL_IN_TEXT = re.compile(r"https?://\S+?\.md")


def _decode_dockey(dockey: str) -> str:
    """searchIndex `docKey` → the blob URL. VERIFIED LIVE against 38 real `cockpit-si-kb` docKeys
    (eval._dockey_investigate, 2026-07): the format is

        <12-hex>_<STANDARD-base64(blob_url + trailing byte)>_pages_<M>

    Three facts confirmed live, correcting the old naïve `split("_")[1]` decode which fell back to the
    RAW base64 for ~half the docKeys (giving broken citations):

      1. The base64 alphabet is **standard** (`+`/`/`), NOT url-safe — for keys where the two alphabets
         diverge, only `base64.b64decode` recovers the URL.
      2. The middle segment encodes `blob_url` PLUS a glued trailing byte (a page-number char / `\r`), so
         raw decode yields the URL followed by 1-3 garbage chars past `.md` — we extract the `…​.md` URL.
      3. Padding is stripped in the wire form, and the segment length is sometimes ≡ 1 (mod 4), which is
         structurally invalid base64 → the old code threw and fell back to raw. Dropping the glued tail
         byte(s) (try trims 0..3) restores a valid, decodable segment.

    Strategy: strip the `<12hex>_` prefix and the trailing `_pages_<M>` suffix (regex — NOT split-and-take,
    which would mangle a base64 body that contained the delimiter), then decode standard base64 tolerating
    the glued tail byte, and return the first `https://…​.md` URL found. Safe readable fallback (the raw
    docKey) only if nothing plausible decodes."""
    seg = _DOCKEY_PAGES_SUFFIX.sub("", _DOCKEY_HEX_PREFIX.sub("", dockey, count=1))
    for trim in range(4):  # tolerate the glued page-number/tail byte: try dropping 0..3 trailing chars
        candidate = seg[: len(seg) - trim] if trim else seg
        try:
            text = base64.b64decode(candidate + "=" * (-len(candidate) % 4)).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        m = _BLOB_URL_IN_TEXT.search(text)
        if m:
            return m.group(0)
    return dockey  # readable fallback — only if no plausible blob URL decodes


def _sourcedata_snippet(ref: dict) -> str:
    """The per-reference snippet from `references[].sourceData` — the PRIMARY, VERIFIED-LIVE carrier.

    With `includeReferenceSourceData=true` on the ksp (see `_native_retrieve`), every reference carries
    `sourceData = {uid, blob_url, snippet}` populated from the KS's `source_data_fields`. `snippet` is the
    verbatim grounding text for that citation — exactly what the UI shows on click. Verified live against
    `cockpit-si-kb`: 39/39 (User A) and 37/37 (User B) references returned a non-empty `snippet`.

    Fallback to `content` covers a KS whose source_data_fields expose the chunk under `content` instead of
    `snippet` (the extractedData chunk key); empty string if neither is present (never a wrong snippet)."""
    sd = ref.get("sourceData")
    if not isinstance(sd, dict):
        return ""
    return str(sd.get("snippet") or sd.get("content") or "")


def _parse_native(body: dict) -> list[dict]:
    """references[] → raw rows [{source, url, snippet}].

    `references[].docKey` decodes (see `_decode_dockey`, VERIFIED LIVE) to the blob_url → `source` =
    filename, `url` = blob_url. The `snippet` comes from `references[].sourceData.snippet` — the per-
    reference grounding text populated by `includeReferenceSourceData=true` (see `_native_retrieve` and
    `_sourcedata_snippet`), VERIFIED LIVE. This replaces the old `id`↔`response`-chunk `ref_id` join,
    which never fired on the `answerSynthesis` KB (there `response` is the prose answer, not a JSON chunk
    array, and — without the flag — `sourceData` came back null, so every snippet was empty)."""
    rows: list[dict] = []
    for ref in body.get("references", []) or []:
        dockey = ref.get("docKey")
        if not dockey:
            continue
        blob_url = _decode_dockey(str(dockey))
        source = blob_url.rsplit("/", 1)[-1] if blob_url else str(dockey)
        snippet = _sourcedata_snippet(ref)
        rows.append({"source": source, "url": blob_url, "snippet": snippet})
    return rows


async def _direct_search_authorized(
    domain, query: str, primary_token: str, user_token: str | None, *, top: int = 8
) -> list[dict]:
    """FALLBACK engine — DIRECT search over `domain.search_index` AS THE USER. The service trims by the
    stamped `groups` field (permissionFilterOption enabled), so the result contains ONLY documents the
    user may read. Returns raw rows [{source, url, snippet}] (dedup + 1-based reindex happen in _project).
    This is where per-user ACL works on non-searchIndex-KB domains."""
    import httpx

    headers = {"Authorization": f"Bearer {primary_token}", "Content-Type": "application/json"}
    if user_token:
        headers["x-ms-query-source-authorization"] = user_token  # the ACL trim (real per-user)
    else:
        # Dev / auth-off: no caller identity. Elevated-read returns all docs so local dev isn't
        # fail-closed to public-only. Best-effort — if the identity lacks the elevated permission,
        # the query still runs (returns whatever the primary identity is entitled to).
        headers["x-ms-enable-elevated-read"] = "true"
    url = f"{domain.search_endpoint.rstrip('/')}/indexes/{domain.search_index}/docs/search?api-version={_KB_API}"
    payload = {"search": query, "select": "snippet,blob_url", "top": top}
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        rows = resp.json().get("value", [])
    return [
        {"source": (r.get("blob_url") or "").rsplit("/", 1)[-1], "url": r.get("blob_url") or "",
         "snippet": r.get("snippet") or ""}
        for r in rows
    ]


def _project(rows: list[dict]) -> list[dict]:
    """Centralized dedup-by-URL (first-wins) + 1-based reindex → [{index, source, url, snippet}].

    Both engines feed through here, so index/dedup semantics live in exactly one place."""
    docs: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        url = r.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        docs.append({
            "index": len(docs) + 1,
            "source": r.get("source") or (url.rsplit("/", 1)[-1] if url else ""),
            "url": url,
            "snippet": r.get("snippet") or "",
        })
    return docs
