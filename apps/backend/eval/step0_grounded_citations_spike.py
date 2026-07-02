"""STEP 0 spike — verify the grounded-citations approach (spec 2026-07-01) against LIVE Foundry+Search.

Throwaway verification (NOT a product test). Proves, before any product code:
  (shape) the inline Responses + MCP knowledge_base_retrieve tool call shape (A1 inline vs A2 needs
          a project connection);
  (a)     citations/annotations come back → capture the exact structure + the annotation→sources mapping;
  (b)     no 403 on raw inference under a USER token (the in-session 200; the MI 403 was a service principal).

ACL (c) and the frontend channel are verified separately (need test users / a browser).

Run (as a signed-in user, live infra):
    cd apps/backend && uv run python -m eval.step0_grounded_citations_spike
Skips cleanly if the infra env is absent.
"""

from __future__ import annotations

import asyncio
import json
import sys

from app.core.tenant import tenant_config

_API = "2026-05-01-preview"
_PROBE = "Quais são os servidores MCP do Cockpit e o que cada um faz?"
_CITE = (
    "Use a ferramenta da base de conhecimento para responder. Se não estiver na base, diga que não sabe. "
    "Toda afirmação deve trazer anotações da ferramenta e renderizá-las como 【message_idx:search_idx†source_name】."
)


def _dump(label: str, obj: object) -> None:
    print(f"\n--- {label} ---")
    try:
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str)[:4000])
    except Exception:  # noqa: BLE001
        print(repr(obj)[:4000])


async def _run() -> int:
    cfg = tenant_config()
    search = (cfg.azure_search_endpoint or "").rstrip("/")
    project = cfg.foundry_project_endpoint or ""
    kb = cfg.cockpit_search_knowledge_base
    if not (search and project and kb):
        print("SKIP: STEP 0 needs live Foundry+Search (AZURE_SEARCH_ENDPOINT, FOUNDRY_PROJECT_ENDPOINT, cockpit KB).")
        return 0

    from azure.ai.projects.aio import AIProjectClient
    from azure.identity.aio import DefaultAzureCredential

    server_url = f"{search}/knowledgebases/{kb}/mcp?api-version={_API}"
    mcp_tool = {
        "type": "mcp",
        "server_label": "knowledge-base",
        "server_url": server_url,
        "allowed_tools": ["knowledge_base_retrieve"],
        "require_approval": "never",
    }
    print(f"probe KB      : {kb}")
    print(f"mcp server_url: {server_url}")

    credential = DefaultAzureCredential()
    # Primary auth for the MCP server (Azure Search KB) = a search-scoped bearer (Search Index Data
    # Reader). Distinct from the per-user ACL header (x-ms-query-source-authorization). Spec §2 "two
    # auth layers". For this shape/citation spike we use our own user token for both.
    search_tok = (await credential.get_token("https://search.azure.com/.default")).token
    mcp_tool["authorization"] = search_tok  # A1-with-auth: inline primary auth, no project connection
    proj = AIProjectClient(endpoint=project, credential=credential, allow_preview=True)
    client = proj.get_openai_client()
    client = await client if asyncio.iscoroutine(client) else client

    rc = 1
    try:
        # A1-with-auth: fully inline (no project connection), MCP primary auth via the `authorization` field.
        resp = await client.responses.create(
            model=cfg.foundry_model,
            input=_PROBE,
            instructions=_CITE,
            tools=[mcp_tool],
            stream=False,
        )
        print("\n✅ (b) no 403 — the user token ran raw inference with the inline MCP tool (A1 inline worked).")
        text = getattr(resp, "output_text", None) or ""
        print("\n=== OUTPUT_TEXT (full) ===")
        print(text)
        print("=== END OUTPUT_TEXT ===")
        print(f"\ninline 【…†…】 markers present: {'【' in text}")

        # SOURCES PROJECTION — the exact annotation→{index,source,url,content} mapping for grounded.py.
        sources = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                for a in (getattr(c, "annotations", None) or []):
                    d = a if isinstance(a, dict) else getattr(a, "__dict__", {})
                    url = d.get("url", "")
                    if url.startswith("mcp://"):
                        continue  # synthesis pseudo-cite, not a document
                    title = d.get("title", "") or url
                    sources.append({"source": title.rsplit("/", 1)[-1], "url": url})
        # dedup preserving order, assign 1-based index
        seen, projected = set(), []
        for s in sources:
            if s["url"] in seen:
                continue
            seen.add(s["url"])
            projected.append({"index": len(projected) + 1, **s})
        _dump("SOURCES PROJECTION (deduped, synthesis dropped)", projected)
        # (a) capture the annotation / citation structure — dump everything so we can write the mapping.
        _dump("resp.model_dump() keys", list(getattr(resp, "model_dump", lambda: {})().keys()))
        try:
            full = resp.model_dump()
            _dump("output[] (tool calls + message + annotations)", full.get("output"))
        except Exception as exc:  # noqa: BLE001
            print("model_dump failed:", exc)
        # look for annotations on the message content
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                ann = getattr(c, "annotations", None)
                if ann:
                    _dump("message content annotations", [a if isinstance(a, dict) else a.__dict__ for a in ann])
        rc = 0
    except Exception as exc:  # noqa: BLE001 — capture 403 / MCP-auth / tool errors verbatim
        print("\n❌ inline call raised — capture the exact error for the A1/A2 decision:")
        print(f"   {type(exc).__name__}: {str(exc)[:1500]}")
        print("\n   → If this is a 401/403 FROM the MCP endpoint (not model inference), A1 needs primary auth:")
        print("     retry with a RemoteTool project connection (A2) or an authorization header (spec §2 A1/A2).")
        rc = 2
    finally:
        with __import__("contextlib").suppress(Exception):
            await client.close()
        with __import__("contextlib").suppress(Exception):
            await proj.close()
        with __import__("contextlib").suppress(Exception):
            await credential.close()
    return rc


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
