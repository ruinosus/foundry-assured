"""The Artifacts Studio agent prompt + the wiki-builder pipeline prompts compose
from the DNA scopes ``apps/backend/.dna/studio`` and ``apps/backend/.dna/wiki``
(no inline byte-copies) — ADR-013 phase 3, the tool-calling frontier.

Complements the ``dna eval run studio-prompts`` / ``wiki-prompts`` suites: those
compose via the ``dna`` CLI kernel and guard the *content*; this test additionally
exercises the **Python composition shims** (``app.agents.studio_prompts`` and
``app.knowledge.wiki_prompts``) and proves the app modules that consume them
(``artifacts_studio`` / ``wiki_builder``) import and wire the composed constants —
offline, no live Foundry, no LLM. It also pins the two frontier invariants the
eval suites do not express structurally:

- the wiki page-writer composes the Microsoft depth rules as a *single-source
  Skill* (``.dna/wiki/skills/wiki-page-writer``), and the sibling ``wiki-architect``
  skill does NOT leak into the writer prompt;
- the 4 artifact skills' single source of truth is the same DNA scope
  (``.dna/studio/skills``) the runtime SkillsProvider points at.

    uv run python -m eval.studio_wiki_prompts_compose_test
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

_BACKEND = Path(__file__).resolve().parents[1]  # apps/backend
_SCOPE_DIR = _BACKEND / ".dna"


def main() -> int:
    # Deterministic: compose from the single source in-repo.
    os.environ["DNA_BASE_DIR"] = str(_SCOPE_DIR)

    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'v' if cond else 'x'} {name}")
        if not cond:
            failures.append(name)

    # --- B1: Artifacts Studio -------------------------------------------------
    from app.agents import studio_prompts

    si = studio_prompts.STUDIO_INSTRUCTIONS
    check("studio persona: SINGLE self-contained HTML document",
          "SINGLE self-contained HTML document" in si)
    check("studio pins the mandatory update_artifact tool call",
          "you MUST call the `update_artifact` tool" in si)
    check("studio pins doctype-first complete document",
          "starting with <!doctype html>" in si and "never return a diff or a partial" in si)
    check("studio pins the four artifact types",
          "{report,presentation,walkthrough,dashboard}" in si)
    check("studio follows the SKILL.md via load_skill/read_skill_resource",
          "load_skill/read_skill_resource" in si)

    # The 4 skills are the single source of truth in the DNA scope; the runtime
    # SkillsProvider points at exactly this dir (imported from the shim so the
    # app and the test can never drift on the location).
    sk = studio_prompts.STUDIO_SKILLS_DIR
    check("studio skills single source is .dna/studio/skills",
          sk.is_dir() and sk == _SCOPE_DIR / "studio" / "skills")
    check("studio skills dir has the 4 SKILL.md",
          {"report", "slides", "dashboard", "walkthrough"}
          <= {p.parent.name for p in sk.glob("*/SKILL.md")})

    # The consuming app module wires the composed constant (no inline prompt).
    import app.agents.artifacts_studio as studio_mod
    check("artifacts_studio consumes the composed STUDIO_INSTRUCTIONS",
          studio_mod.STUDIO_INSTRUCTIONS is si)

    # --- C1: wiki-builder pipeline -------------------------------------------
    from app.knowledge import wiki_prompts

    planner = wiki_prompts.WIKI_PLANNER_INSTRUCTIONS
    writer = wiki_prompts.WIKI_PAGE_WRITER_INSTRUCTIONS
    verifier = wiki_prompts.WIKI_VERIFIER_INSTRUCTIONS

    check("planner is the documentation architect with the JSON pages shape",
          "arquiteto de documentação" in planner
          and '{"pages":[{"title":"...","files":["caminho1","caminho2"]}]}' in planner)

    # The writer composes preamble + the Microsoft depth-rules Skill + the adaptations.
    check("writer carries the source-anchored pt-BR persona",
          "ancorada no código real fornecido" in writer)
    check("writer composes the Microsoft wiki-page-writer depth rules (Skill)",
          "TRACE ACTUAL CODE PATHS" in writer and "EVERY CLAIM NEEDS A SOURCE" in writer
          and "Dark-mode colors" in writer)
    check("writer adaptations OVERRIDE the skill (no git/tools, markdown-only)",
          "não use git/tools" in writer and "sem frontmatter VitePress" in writer)
    # Single-source frontier: the sibling wiki-architect Skill must NOT leak into
    # the writer prompt (only the referenced skill composes).
    check("wiki-architect does NOT leak into the writer prompt",
          "documentation architect that produces structured wiki catalogues" not in writer)
    # The depth rules appear once (composed once), not duplicated.
    check("writer composes the depth rules exactly once (no duplication)",
          writer.count("# Wiki Page Writer") == 1)

    check("verifier is the strict fidelity checker",
          "verificador de FIDELIDADE rigoroso" in verifier
          and "Não adicione informação nova" in verifier)
    check("verifier does NOT inherit the writer depth rules",
          "TRACE ACTUAL CODE PATHS" not in verifier)

    # The consuming app module wires the composed constants (no inline strings /
    # no _writer_rules file read).
    import app.knowledge.wiki_builder as wb
    check("wiki_builder consumes the composed writer instruction",
          wb.WIKI_PAGE_WRITER_INSTRUCTIONS is writer)
    check("wiki_builder dropped the _writer_rules() raw file read",
          not hasattr(wb, "_writer_rules") and not hasattr(wb, "_SKILLS_DIR"))

    if failures:
        print(f"\nFAIL: {len(failures)} assertion(s) failed.")
        return 1
    print("\nOK: studio + wiki prompts compose from the DNA scopes (frontier held).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
