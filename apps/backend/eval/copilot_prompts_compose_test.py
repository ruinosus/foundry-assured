"""The Coach-Overlay copilot + artifact prompts compose from the DNA scope
``apps/backend/.dna/copilot/`` (no inline byte-copies) — ADR-013 phase 2.

Imports the ``app.services.prompts`` shim and asserts the composed constants +
the two Python-interpolated PromptTemplate surfaces carry the right sentinels.
Complements the ``dna eval run copilot-prompts`` suite: that suite guards the
five *agent*-composable prompts (refine / extract / extract-stream / edges /
synthesis-base); this test additionally guards the surfaces the eval framework
structurally cannot target — the ``synthesis-tone`` and ``html-artifact``
PromptTemplates, which are NOT prompt targets and are filled per request in
Python (the runtime-dynamic pick that deliberately stays imperative).

Offline + deterministic (contains / not-contains over composed text) — no live
Foundry, no LLM. Points DNA_BASE_DIR at apps/backend/.dna so it composes from
the single source regardless of any external mount.

    uv run python -m eval.copilot_prompts_compose_test
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

_BACKEND = Path(__file__).resolve().parents[1]  # apps/backend
_SCOPE_DIR = _BACKEND / ".dna"


def main() -> int:
    # Deterministic: compose from the single source in-repo.
    os.environ["DNA_BASE_DIR"] = str(_SCOPE_DIR)

    # Import AFTER setting DNA_BASE_DIR so the shim composes from the repo scope.
    from app.services import prompts

    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'v' if cond else 'x'} {name}")
        if not cond:
            failures.append(name)

    # --- refine (B4) --------------------------------------------------------
    check("refine asks for ONE clean pt-BR question",
          "UMA pergunta técnica clara e concisa" in prompts.REFINE_INSTRUCTIONS)
    check("refine is answer-only (no preamble)",
          "sem preâmbulo, sem aspas, sem explicação" in prompts.REFINE_INSTRUCTIONS)
    check("refine does NOT inherit the extractor Soul",
          "Extraia até 6 itens" not in prompts.REFINE_INSTRUCTIONS)

    # --- extract (B5) — shared persona + STT skill + JSON delta -------------
    check("extract carries the shared extractor persona",
          "Extraia até 6 itens NOVOS" in prompts.EXTRACT_INSTRUCTIONS)
    check("extract pins the JSON node shape",
          '"nodes":[{"type":"...","label":"...","detail":"..."}]' in prompts.EXTRACT_INSTRUCTIONS)
    check("extract carries the shared STT-correction few-shot",
          "'dot net'→'.NET'" in prompts.EXTRACT_INSTRUCTIONS)
    check("extract is NOT the streaming line variant",
          "type|label|detail" not in prompts.EXTRACT_INSTRUCTIONS)

    # --- extract-stream (B6) — same persona + SAME skill + line delta -------
    check("extract-stream pins the pipe line format",
          "type|label|detail" in prompts.EXTRACT_STREAM_INSTRUCTIONS)
    check("extract-stream reuses the SAME STT few-shot (Avanade)",
          "'Havanadia'→'Avanade'" in prompts.EXTRACT_STREAM_INSTRUCTIONS
          and "'dot net'→'.NET'" in prompts.EXTRACT_STREAM_INSTRUCTIONS)
    check("extract-stream is NOT the JSON variant",
          '"nodes":' not in prompts.EXTRACT_STREAM_INSTRUCTIONS)
    # Consolidation invariant: the STT few-shot is authored ONCE (a Skill), so
    # both extractors carry byte-identical correction text.
    _stt = "A transcrição tem ERROS de reconhecimento de fala"
    check("STT few-shot is shared verbatim by both extractors (no duplication)",
          _stt in prompts.EXTRACT_INSTRUCTIONS and _stt in prompts.EXTRACT_STREAM_INSTRUCTIONS)

    # --- edges (B7) ---------------------------------------------------------
    check("edges caps at 4 and pins the from/to JSON shape",
          "NO MÁXIMO 4 arestas" in prompts.EDGES_INSTRUCTIONS
          and '"edges":[{"from":"<id>","to":"<id>"}]' in prompts.EDGES_INSTRUCTIONS)
    check("edges does NOT inherit the extractor Soul",
          "Extraia até 6 itens" not in prompts.EDGES_INSTRUCTIONS)

    # --- synthesis base (B3) — tone-free grounded pt-BR ---------------------
    check("synthesis base is grounded pt-BR with [n] citations",
          "APENAS com base nos documentos" in prompts.SYNTHESIS_INSTRUCTIONS
          and "não há informação suficiente" in prompts.SYNTHESIS_INSTRUCTIONS)
    check("synthesis base carries NO tone (tone is a separate PromptTemplate)",
          "Tom de negócio" not in prompts.SYNTHESIS_INSTRUCTIONS)

    # --- synthesis-tone PromptTemplate — the RIGHT tone per meeting_type ----
    # (the eval suite can't target a PromptTemplate; guard the Python lookup here)
    expected_tone = {
        "presentation": "Tom de negócio: foque benefícios e arquitetura de alto nível.",
        "technical": "Tom técnico: pode citar detalhes de implementação.",
        "sales": "Tom comercial: foque valor, segurança e escalabilidade.",
        "interview": "Tom conceitual: foque trade-offs e o porquê das decisões.",
    }
    for mt, snippet in expected_tone.items():
        composed = prompts.synthesis_instructions(mt)
        check(f"synthesis tone[{mt}] appends the right variant",
              composed.startswith(prompts.SYNTHESIS_INSTRUCTIONS) and snippet in composed)
    # An unknown meeting type yields the base alone (no tone) — matches the old
    # dict.get(meeting_type, "") default.
    check("synthesis tone[unknown] == base (no tone)",
          prompts.synthesis_instructions("bogus") == prompts.SYNTHESIS_INSTRUCTIONS)
    # No tone bleed across variants.
    check("synthesis tone[technical] excludes the sales tone",
          "Tom comercial" not in prompts.synthesis_instructions("technical"))

    # --- html-artifact PromptTemplate (B2) ----------------------------------
    html = prompts.html_artifact_instructions("report")
    check("html artifact demands a SINGLE self-contained document",
          "SINGLE self-contained" in html and "safe to render inside a sandboxed iframe" in html)
    check("html artifact returns ONLY the doc, doctype-first",
          "Return ONLY the HTML, starting with <!doctype html>" in html)
    check("html artifact fills the per-request type",
          html.rstrip().endswith("Artifact type: report.")
          and prompts.html_artifact_instructions("dashboard").rstrip().endswith("Artifact type: dashboard."))

    if failures:
        print(f"\nFAIL: {len(failures)} assertion(s) failed.")
        return 1
    print("\nOK: copilot + artifact prompts compose from the DNA scope.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
