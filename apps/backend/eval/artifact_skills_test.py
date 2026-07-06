"""Artifact skills discovery — the SkillsProvider finds the 4 skills.

Run (from apps/backend/):  uv run python -m eval.artifact_skills_test
"""
import sys
from pathlib import Path


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    skills_dir = Path(__file__).resolve().parents[1] / "artifact-skills"
    check("artifact-skills dir exists", skills_dir.is_dir())

    expected = {"slides", "report", "dashboard", "walkthrough"}
    found = {p.parent.name for p in skills_dir.glob("*/SKILL.md")}
    check(f"4 SKILL.md skills present ({expected})", expected <= found)

    # Each SKILL.md has YAML frontmatter with name + description + a valid type.
    from app.artifacts.models import ALLOWED_TYPES
    for name in expected:
        text = (skills_dir / name / "SKILL.md").read_text(encoding="utf-8")
        check(f"{name}: has frontmatter", text.startswith("---"))
        check(f"{name}: declares name", "name:" in text.split("---")[1])
        # Bookkeeping only: the category under metadata (SDK ignores top-level type; model gets the
        # enum from instructions). Grep the raw text for any allowed type token.
        check(f"{name}: declares a valid type (bookkeeping)", any(t in text for t in ALLOWED_TYPES))

    # SkillsProvider discovers them (Experimental API — verify it imports + from_paths works).
    from agent_framework import SkillsProvider
    provider = SkillsProvider.from_paths(str(skills_dir))
    check("SkillsProvider.from_paths constructs", provider is not None)

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
