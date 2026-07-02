"""Infra-free: grounded.py builds the correct synthesis payload, without touching Azure.

ONE archetype now — `build_synthesis_kwargs` puts the retrieved docs as the model's ONLY grounding
context (the retrieved snippets), cited by [n]; empty set → fail-closed "não sei".

    cd apps/backend && uv run python -m eval.grounded_payload_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.services.grounded import SYNTHESIS_DIRECTIVE, build_synthesis_kwargs


def main() -> None:
    domain = SimpleNamespace(instructions="X")
    docs = [
        {"index": 1, "source": "a.md", "url": "https://x/a.md", "snippet": "conteudo A"},
        {"index": 2, "source": "b.md", "url": "https://x/b.md", "snippet": "conteudo B"},
    ]
    sk = build_synthesis_kwargs("qual a resposta?", domain, docs, model="m")
    assert sk["model"] == "m" and sk["stream"] is True, sk
    assert "tools" not in sk, sk  # synthesis has no MCP tool — docs are the ONLY context
    assert sk["instructions"] == "X", sk
    assert SYNTHESIS_DIRECTIVE in sk["input"]
    assert "[1] a.md" in sk["input"] and "conteudo A" in sk["input"]  # docs are the grounding context
    assert "qual a resposta?" in sk["input"]

    # empty authorized set → still asks, but with no docs (fail-closed to "não sei")
    empty = build_synthesis_kwargs("q", domain, [], model="m")
    assert "Nenhum documento autorizado" in empty["input"]

    print("PASS: grounded synthesis payload (retrieved docs are the only grounding context)")
    sys.exit(0)


if __name__ == "__main__":
    main()
