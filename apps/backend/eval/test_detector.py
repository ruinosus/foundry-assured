"""Unit tests for the copilot question detector (heuristic)."""

from app.agents.detector import detect_question


def test_flags_question_by_marker():
    r = detect_question([{"speaker": "SPEAKER_01", "text": "Como funciona a infra?"}])
    assert r["is_question"] is True
    assert r["question_text"] == "Como funciona a infra?"
    assert r["confidence"] > 0


def test_flags_question_by_question_mark():
    r = detect_question([{"speaker": "SPEAKER_01", "text": "Isso escala bem em produção?"}])
    assert r["is_question"] is True


def test_ignores_statements():
    r = detect_question([{"speaker": "SPEAKER_01", "text": "Legal, entendi tudo."}])
    assert r["is_question"] is False
    assert r["question_text"] == ""


def test_ignores_too_short():
    # interrogative opener but < 3 words → not a question worth answering
    r = detect_question([{"speaker": "SPEAKER_01", "text": "Qual?"}])
    assert r["is_question"] is False


def test_empty_window():
    r = detect_question([])
    assert r["is_question"] is False


def test_classifies_only_the_tail():
    r = detect_question(
        [
            {"speaker": "SPEAKER_00", "text": "Como funciona X?"},  # earlier question
            {"speaker": "SPEAKER_01", "text": "Perfeito, obrigado."},  # tail = statement
        ]
    )
    assert r["is_question"] is False
