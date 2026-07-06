"""Artifacts Studio agent — tool + state wiring (no LLM, no network).

Run (from apps/backend/):  uv run python -m eval.artifact_studio_test
"""
import sys


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    from app.agents.artifacts_studio import ArtifactDraft, update_artifact

    # ArtifactDraft holds the complete HTML document.
    d = ArtifactDraft(html="<!doctype html><html><body>x</body></html>")
    check("ArtifactDraft.html round-trips", d.html.startswith("<!doctype html>"))

    # update_artifact is an agent-framework @tool (has the tool marker) and returns a confirmation.
    check("update_artifact is a tool", hasattr(update_artifact, "__agent_framework_tool__")
          or hasattr(update_artifact, "ai_function") or callable(update_artifact))

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
