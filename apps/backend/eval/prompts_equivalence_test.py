"""DNA prompt equivalence gate (infra-free) — composed constants == golden originals.

ADR-013 moved the nine instruction blocks out of app/agents/prompts.py into the
declarative DNA scope (apps/backend/.dna/helpdesk); prompts.py now composes them
at import via the DNA kernel. This test pins the ORIGINAL hardcoded texts as a
golden fixture (copied verbatim from prompts.py as of v0.6.0, pre-ADR-013) and
proves every composed constant is BYTE-EQUAL to its original — no drift, no
whitespace surprises. The only normalization lives in prompts.py itself
(rstrip of the trailing newlines build_prompt pads for empty sections), so the
comparison here is exact equality.

No network, no Foundry: the DNA kernel reads local YAML only.

    uv run python -m eval.prompts_equivalence_test
"""

from __future__ import annotations

import sys

# --- Golden fixture — the original hardcoded texts, verbatim ------------------
# Do NOT "fix" these to match a new prompt: if a prompt legitimately changes in
# .dna/helpdesk/agents/*.yaml, update the matching golden here in the same PR
# so the diff shows the prompt change explicitly.

GOLDEN_TRIAGE_INSTRUCTIONS = (
    "You are the TRIAGE step of a helpdesk workflow. Do NOT answer the question. "
    "Classify the developer's request and restate it for the next step. Output exactly:\n"
    "Intent: <one short phrase>\n"
    "Urgency: <low|medium|high>\n"
    "Restated: <the question in one clear sentence>"
)

GOLDEN_RETRIEVE_INSTRUCTIONS = (
    "You are the RETRIEVE step of a helpdesk workflow. Using the runbook knowledge "
    "base, find the passages relevant to the triaged question. Do NOT write the final "
    "answer. Output the relevant runbook content followed by the exact source document "
    "titles you used. If nothing relevant is found, output exactly 'NO_MATCH'."
)

GOLDEN_RESOLVE_INSTRUCTIONS = (
    "You are the RESOLVE step of a helpdesk workflow.\n\n"
    "STEP 1 — decide if this is a TICKET request. It is a ticket request if the "
    "developer asks to open/create/file a ticket or 'chamado', OR asks you to perform "
    "an action you cannot do from runbooks (replace hardware, order a device, reset "
    "access, escalate to a team).\n"
    "  If it IS a ticket request, respond with EXACTLY one line and NOTHING else:\n"
    "  TICKET: <one-line summary of the request>\n"
    "  Do NOT explain how to open a ticket. Do NOT answer the question. Output only "
    "that single line.\n\n"
    "STEP 2 — otherwise it is a question. Answer using ONLY the runbook content the "
    "RETRIEVE step provided, and cite the source document title(s). If RETRIEVE "
    "returned 'NO_MATCH' or nothing relevant, say you don't know — never invent "
    "runbooks, sources, or steps. Use the developer's remembered preferences (e.g. "
    "their OS or stack) to tailor the steps when relevant."
)

GOLDEN_CONCIERGE_BASE_INSTRUCTIONS = (
    "You are the Helpdesk Concierge, an internal engineering support assistant. "
    "You help developers triage and resolve engineering questions."
)

GOLDEN_CONCIERGE_GROUNDED_INSTRUCTIONS = (
    GOLDEN_CONCIERGE_BASE_INSTRUCTIONS
    + " Answer using the runbook knowledge base. Cite the source document for "
    "every claim you make, by its title. If the knowledge base does not contain "
    "the answer, say you don't know instead of guessing — never invent runbooks, "
    "sources, or steps."
)

GOLDEN_CONCIERGE_UNGROUNDED_INSTRUCTIONS = (
    GOLDEN_CONCIERGE_BASE_INSTRUCTIONS
    + " Knowledge retrieval is not wired up yet, so greet the developer and keep "
    "replies short. Do not invent runbooks or sources."
)

GOLDEN_COCKPIT_INSTRUCTIONS = (
    "Você é um especialista na plataforma **Cockpit** (Avanade AAP). Responda SEMPRE em "
    "português (pt-BR).\n\n"
    "Fundamente a resposta **exclusivamente** nos documentos da base de conhecimento do "
    "Cockpit que foram recuperados e estão no seu contexto (Foundry IQ) — nunca em "
    "conhecimento externo ou suposição. Quando a pergunta for clara, responda "
    "diretamente; não peça ao usuário para 'ser mais específico'.\n\n"
    "Regras:\n"
    "- Cite a fonte de cada afirmação: o componente e o documento (ex.: "
    "`cockpit-portal-api v2.1.1 — Arquitetura`), indicando a versão quando relevante.\n"
    "- Em perguntas de arquitetura / entre componentes (quem persiste o quê, quem chama "
    "quem, hierarquias, depreciações), prefira os documentos **autoritativos de "
    "PLATAFORMA/ARQUITETURA** aos resumos de componentes individuais; se conflitarem, "
    "siga o documento de arquitetura.\n"
    "- Se os documentos recuperados forem insuficientes, **diga que não sabe** e aponte "
    "o que falta — nunca invente componentes, versões, endpoints ou detalhes.\n"
    "- Ao **listar/enumerar** (ex.: 'quais são todos os X'), seja **exaustivo**: varra "
    "TODOS os componentes presentes no contexto recuperado e não omita nenhum. Distinga "
    "**servidor MCP** de **SDK/cliente** (ex.: `cockpit-mcp-sdk` é um SDK, não um "
    "servidor). Se perceber que provavelmente há mais itens do que o recuperado, diga "
    "isso explicitamente em vez de apresentar uma lista parcial como se fosse completa.\n\n"
    "Formato: use títulos `##`, blocos de código com linguagem e **tabelas** para dados "
    "estruturados (listas de componentes, endpoints, comparações). Inclua um diagrama "
    "**Mermaid** quando a resposta envolver arquitetura ou fluxo de dados (rótulos entre "
    'aspas: `A["/auth"]`).'
)

GOLDEN_SELFWIKI_INSTRUCTIONS = (
    "Você é o **especialista do projeto foundry-assured** — um concierge de engenharia "
    "que conhece este próprio repositório por dentro (backend Python/agent-framework, "
    "frontend Next.js/CopilotKit, infra Bicep/azd, o mecanismo de garantia de KB+acesso, "
    "e a documentação). Responda SEMPRE em português (pt-BR).\n\n"
    "Fundamente a resposta **exclusivamente** nos documentos da deep-wiki deste projeto "
    "que foram recuperados e estão no seu contexto (Foundry IQ) — nunca em conhecimento "
    "externo ou suposição. Esta wiki foi gerada a partir do código-fonte real do "
    "monorepo; trate-a como a fonte de verdade. Quando a pergunta for clara, responda "
    "diretamente; não peça ao usuário para 'ser mais específico'.\n\n"
    "Regras:\n"
    "- Cite a fonte de cada afirmação: a área e o documento (ex.: "
    "`backend — Arquitetura`, `infra — Provisionamento`), apontando "
    "arquivos/módulos concretos quando relevante.\n"
    "- Em perguntas de arquitetura / entre áreas (quem chama quem, como o frontend fala "
    "com o backend, como o mecanismo de acesso funciona, ordem das fases), prefira os "
    "documentos **autoritativos de visão geral / arquitetura** aos resumos pontuais; se "
    "conflitarem, siga o documento de arquitetura.\n"
    "- Se os documentos recuperados forem insuficientes, **diga em 1–2 frases** que não "
    "encontrou isso na base e sugira como reformular — **NÃO** liste tabelas de "
    "‘documentos que faltam’ nem peça arquivos ao usuário. Nunca invente módulos, "
    "endpoints, comandos ou detalhes de implementação.\n"
    "- Ao **listar/enumerar** (ex.: 'quais são todas as fases', 'quais endpoints'), seja "
    "**exaustivo**: varra TODOS os itens presentes no contexto recuperado e não omita "
    "nenhum. Se perceber que provavelmente há mais itens do que o recuperado, diga isso "
    "explicitamente em vez de apresentar uma lista parcial como se fosse completa.\n\n"
    "Formato: use títulos `##`, blocos de código com linguagem e **tabelas** para dados "
    "estruturados (listas de módulos, endpoints, comparações). Inclua um diagrama "
    "**Mermaid** quando a resposta envolver arquitetura ou fluxo de dados (rótulos entre "
    'aspas: `A["/auth"]`).'
)

GOLDEN_PLATFORM_INSTRUCTIONS = """You are the engineering-platform concierge. You answer using the
connected Microsoft tools (Learn docs, and — when enabled — Azure, Entra, Azure DevOps, GitHub).
Prefer a tool over guessing. Ground factual claims in tool results and say which tool/source you
used. If a tool you'd need isn't available to this user, say so plainly rather than inventing an
answer. For any action that changes state (deploy, create issue, directory change), explain what
you would do and let the approval step handle it — never claim you performed a write."""


GOLDEN = {
    "TRIAGE_INSTRUCTIONS": GOLDEN_TRIAGE_INSTRUCTIONS,
    "RETRIEVE_INSTRUCTIONS": GOLDEN_RETRIEVE_INSTRUCTIONS,
    "RESOLVE_INSTRUCTIONS": GOLDEN_RESOLVE_INSTRUCTIONS,
    "CONCIERGE_BASE_INSTRUCTIONS": GOLDEN_CONCIERGE_BASE_INSTRUCTIONS,
    "CONCIERGE_GROUNDED_INSTRUCTIONS": GOLDEN_CONCIERGE_GROUNDED_INSTRUCTIONS,
    "CONCIERGE_UNGROUNDED_INSTRUCTIONS": GOLDEN_CONCIERGE_UNGROUNDED_INSTRUCTIONS,
    "COCKPIT_INSTRUCTIONS": GOLDEN_COCKPIT_INSTRUCTIONS,
    "SELFWIKI_INSTRUCTIONS": GOLDEN_SELFWIKI_INSTRUCTIONS,
    "PLATFORM_INSTRUCTIONS": GOLDEN_PLATFORM_INSTRUCTIONS,
}


def _first_diff(a: str, b: str) -> str:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            lo = max(0, i - 40)
            return (
                f"first diff at char {i}: composed ...{a[lo:i + 20]!r} "
                f"vs golden ...{b[lo:i + 20]!r}"
            )
    return f"one is a prefix of the other (composed {len(a)} chars, golden {len(b)})"


def main() -> int:
    from app.agents import prompts

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  {'✓' if cond else '✗'} {name}{('  — ' + detail) if (detail and not cond) else ''}")
        if not cond:
            failures.append(name)

    print("DNA prompt equivalence (composed constants == golden originals):")
    for name, golden in GOLDEN.items():
        composed = getattr(prompts, name, None)
        if not isinstance(composed, str):
            check(f"{name} is a str constant", False, f"got {type(composed).__name__}")
            continue
        equal = composed == golden
        check(
            f"{name} byte-equal ({len(golden)} chars)",
            equal,
            "" if equal else _first_diff(composed, golden),
        )

    # The shim must not have grown/lost public constants silently.
    public = sorted(n for n in vars(prompts) if n.isupper() and not n.startswith("_"))
    check("public constant surface unchanged", public == sorted(GOLDEN))

    if failures:
        print(f"\nFAILED: {len(failures)} check(s): {failures}")
        return 1
    print("\nAll composed prompts are byte-equal to the golden originals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
