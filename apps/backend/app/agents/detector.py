"""Detect whether the tail of a transcript window is a technical question worth answering.

Phase 2: cheap deterministic heuristic (question marker + interrogative starts + min length).
Phase 2b (optional): swap `detect_question` for an LLM classifier built with
client.as_agent(...) — ONLY if the heuristic's false-positive rate proves too high in real calls.

Kept as a plain module-level function (not a fake "agent" class): the repo only builds
agent-framework Agents when it needs an LLM, and this stage doesn't.
"""
from __future__ import annotations

# Portuguese interrogative openers. A statement rarely starts with these + has >=3 words.
_STARTS = (
    "como",
    "qual",
    "quais",
    "por que",
    "porque",
    "por quê",
    "o que",
    "quando",
    "onde",
    "quanto",
    "quantos",
    "quantas",
    "pode",
    "poderia",
    "consegue",
    "existe",
    "tem como",
)


def detect_question(transcript_window: list[dict]) -> dict:
    """Return {is_question, question_text, confidence} for the LAST utterance in the window.

    `transcript_window` is a list of {speaker, text} dicts (the overlay keeps the last ~5).
    We only classify the tail — an utterance is a question if it contains "?" OR opens with an
    interrogative word, AND has at least 3 words (filters "Como assim?" one-word noise less, and
    avoids firing on tiny backchannel like "Qual?").
    """
    if not transcript_window:
        return {"is_question": False, "question_text": "", "confidence": 0.0}

    text = (transcript_window[-1].get("text") or "").strip()
    low = text.lower()
    is_q = ("?" in text or low.startswith(_STARTS)) and len(text.split()) >= 3

    return {
        "is_question": bool(is_q),
        "question_text": text if is_q else "",
        "confidence": 0.8 if is_q else 0.0,
    }
