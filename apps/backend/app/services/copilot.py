"""Copilot answer service — the honest reuse layer.

Fans the PURE `retrieve()` seam over the cockpit + selfwiki KBs, merges + globally reindexes
the docs, then synthesizes ONE cited answer with the SAME `build_synthesis_kwargs()` the
grounded archetype uses. No WorkflowBuilder, no new SDK surface. Returns plain JSON so the Coach
Overlay never has to parse AG-UI SSE.

Verified against foundry-helpdesk:
- retrieve(query, user, domain, *, top=8) -> [{index, source, url, snippet}]  (app/services/retrieval.py)
- build_synthesis_kwargs(user_text, domain, docs, *, model) -> dict           (app/services/grounded.py)
- _async_credential(user)                                                      (app/services/grounded.py)
"""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import time
from dataclasses import replace

from app.core.tenant import tenant_config
from app.domains import get_domain
from app.services.grounded import build_synthesis_kwargs
from app.services.retrieval import retrieve

# The two grounded KBs the copilot searches. cockpit-si-kb + selfwiki-si-kb are already indexed.
COPILOT_DOMAINS = ("cockpit", "selfwiki")

# Cap the docs fed to synthesis. The native KB retrieve returns the KB's full default set (~31 for
# cockpit) — passing all of them makes a huge prompt (slow + expensive). The top few (already in
# relevance order) are plenty for a 2–4 sentence answer, and keep the card's source list readable.
MAX_DOCS = 8


class _CopilotDomain:
    """Duck-typed domain for synthesis: build_synthesis_kwargs only reads `.instructions`."""

    def __init__(self, instructions: str) -> None:
        self.instructions = instructions


def _instructions_for(meeting_type: str) -> str:
    """Synthesis instructions with a tone adapted to the meeting type."""
    base = (
        "Você ajuda o apresentador a responder uma pergunta técnica feita numa call. "
        "Responda de forma curta (2–4 frases), em português, APENAS com base nos documentos "
        "fornecidos, citando cada afirmação pelo seu número entre colchetes, ex.: [1]. "
        "Se os documentos não contiverem a resposta, diga que não há informação suficiente."
    )
    tone = {
        "presentation": " Tom de negócio: foque benefícios e arquitetura de alto nível.",
        "technical": " Tom técnico: pode citar detalhes de implementação.",
        "sales": " Tom comercial: foque valor, segurança e escalabilidade.",
        "interview": " Tom conceitual: foque trade-offs e o porquê das decisões.",
    }.get(meeting_type, "")
    return base + tone


async def _responses(instructions: str, input_text: str, user) -> str:
    """One non-streaming Foundry Responses call AS THE USER (OBO) / app identity (dev). Returns text.

    RULE #1: the non-streaming output field is read via `getattr(resp, "output_text", "")`. Confirm
    against the installed azure-ai-projects / openai SDK before relying on it — don't guess another.
    """
    from azure.ai.projects.aio import AIProjectClient

    from app.services.grounded import _async_credential

    cfg = tenant_config()
    credential = _async_credential(user)
    proj = AIProjectClient(
        endpoint=cfg.foundry_project_endpoint, credential=credential, allow_preview=True
    )
    try:
        client = proj.get_openai_client()
        client = await client if inspect.isawaitable(client) else client
        resp = await client.responses.create(
            model=cfg.foundry_model, instructions=instructions, input=input_text, stream=False
        )
        return getattr(resp, "output_text", "") or ""
    finally:
        for obj in (proj, credential):
            with contextlib.suppress(Exception):
                await obj.close()


async def _synthesize(user_text: str, docs: list[dict], instructions: str, user) -> str:
    """Grounded synthesis: build the docs+directive input via build_synthesis_kwargs, run it."""
    kwargs = build_synthesis_kwargs(
        user_text, _CopilotDomain(instructions), docs, model=tenant_config().foundry_model
    )
    return await _responses(kwargs["instructions"], kwargs["input"], user)


# Consolidate a messy transcript slice (STT errors, fragments) into ONE clean technical question.
REFINE_INSTRUCTIONS = (
    "Você recebe um trecho de transcrição de uma call, que pode conter erros de reconhecimento de "
    "fala, repetições e fragmentos. Consolide em UMA pergunta técnica clara e concisa, em português. "
    "Responda APENAS com a pergunta reformulada — sem preâmbulo, sem aspas, sem explicação."
)


async def refine_question(raw_text: str, user=None) -> str:
    """Turn a raw/garbled transcript slice into a clean question (optional 'run another agent' step)."""
    text = (raw_text or "").strip()
    if not text:
        return ""
    refined = (await _responses(REFINE_INSTRUCTIONS, text, user)).strip()
    return refined or text


async def answer_question(
    question: str, user=None, *, meeting_type: str = "presentation"
) -> dict:
    """Retrieve over both KBs → merge + globally reindex → synthesize one cited answer.

    Returns {answer, sources:[{index, kb, source, url, content}]}.
    """
    t0 = time.monotonic()

    async def _one(dom_id: str) -> list[dict]:
        # Force the FAST direct-search path: the domains have `kb_name`, which routes retrieve()
        # through the Foundry IQ *agentic* KB retrieve — an LLM-powered op that took ~27s. Dropping
        # kb_name makes retrieve() do a plain ACL-trimmed Azure AI Search over `search_index`
        # (~1s), returning the same {source,url,snippet}; WE synthesize once on top (no double-LLM).
        dom = replace(get_domain(dom_id), kb_name=None)
        rows = await retrieve(question, user, dom, top=MAX_DOCS)
        for r in rows:
            r["kb"] = dom_id
        return rows

    # Fan the two KB retrieves out CONCURRENTLY (was sequential → ~2× slower). Fail-soft per KB.
    results = await asyncio.gather(
        *[_one(d) for d in COPILOT_DOMAINS], return_exceptions=True
    )
    docs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            docs.extend(r)
    t1 = time.monotonic()

    # Cap to the top MAX_DOCS (relevance order) BEFORE synthesis, then reindex 1..N so the [n]
    # citations map to `sources`.
    docs = docs[:MAX_DOCS]
    for i, d in enumerate(docs, start=1):
        d["index"] = i

    if not docs:
        return {
            "answer": "Não encontrei informações sobre isso nas KBs (cockpit/selfwiki).",
            "sources": [],
        }

    answer = await _synthesize(question, docs, _instructions_for(meeting_type), user)
    t2 = time.monotonic()
    print(
        f"[copilot] retrieve={t1 - t0:.1f}s synth={t2 - t1:.1f}s docs={len(docs)} q={question[:50]!r}"
    )
    sources = [
        {
            "index": d["index"],
            "kb": d.get("kb"),
            "source": d["source"],
            "url": d["url"],
            "content": (d.get("snippet") or "")[:800],
        }
        for d in docs
    ]
    return {"answer": answer, "sources": sources}


# ── Meeting Board: node extraction ───────────────────────────────────────────
VALID_NODE_TYPES = {"topico", "pergunta", "acao", "ideia"}  # NEVER "kb" — KB is click-only

EXTRACT_INSTRUCTIONS = (
    "Você observa um trecho de transcrição de uma call (pode ter erros de fala). Extraia os itens "
    "NOVOS e relevantes como nós de um mapa. Cada nó tem: type ∈ [topico, pergunta, acao, ideia], "
    "label (curto, ≤6 palavras) e detail (uma frase). Também proponha arestas ligando nós — cada "
    "aresta tem from e to, referenciando um nó existente pelo seu \"id\" (string) OU um nó novo por "
    "{\"newIndex\": N} (índice no array nodes). NÃO invente nós que já existem (veja a lista). "
    "Responda APENAS um JSON com esta forma, sem texto ao redor:\n"
    '{"nodes":[{"type":"...","label":"...","detail":"..."}],'
    '"edges":[{"from":"id-ou-{newIndex}","to":"..."}],'
    '"suggestedQuestion":"..."}'
)


def _strip_json(text: str) -> str:
    """Best-effort: pull the JSON object out of the model text (handles ```json fences / prose)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    return t[start : end + 1] if start != -1 and end != -1 and end > start else t


async def extract_nodes(transcript_window: list[dict], existing_nodes: list[dict], user=None) -> dict:
    """Propose conversation nodes (+ raw edges) from a transcript window. Fail-soft: any parse/shape
    problem returns empty. P1 consumes only `nodes`; `edges` are passed through for P2."""
    empty = {"nodes": [], "edges": [], "suggestedQuestion": None}
    convo = "\n".join(f'{u.get("speaker","?")}: {u.get("text","")}' for u in (transcript_window or []))
    nodes_summary = json.dumps(
        [{"id": n.get("id"), "type": n.get("type"), "label": n.get("label")} for n in (existing_nodes or [])],
        ensure_ascii=False,
    )
    if not convo.strip():
        return empty
    body = f"=== NÓS EXISTENTES ===\n{nodes_summary}\n\n=== TRECHO NOVO ===\n{convo}"
    raw = await _responses(EXTRACT_INSTRUCTIONS, body, user)
    try:
        data = json.loads(_strip_json(raw))
    except Exception:  # noqa: BLE001 — malformed model output must never 500
        return empty
    if not isinstance(data, dict):
        return empty
    nodes = []
    for n in data.get("nodes") or []:
        if isinstance(n, dict) and n.get("type") in VALID_NODE_TYPES and (n.get("label") or "").strip():
            nodes.append({"type": n["type"], "label": n["label"].strip(), "detail": (n.get("detail") or "").strip()})
    edges = data.get("edges") if isinstance(data.get("edges"), list) else []
    sq = data.get("suggestedQuestion")
    return {"nodes": nodes, "edges": edges, "suggestedQuestion": sq if isinstance(sq, str) else None}
