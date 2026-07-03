"""Unit tests for the copilot answer service (retrieve fan-out + merge/reindex).

The Foundry synthesis is mocked so the test is offline-safe."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services import copilot


class _Dom:
    def __init__(self, id):
        self.id = id


@pytest.mark.asyncio
async def test_answer_question_merges_two_kbs_and_reindexes():
    fake_cockpit = [{"index": 1, "source": "a.md", "url": "u1", "snippet": "A"}]
    fake_selfwiki = [{"index": 1, "source": "b.md", "url": "u2", "snippet": "B"}]

    async def fake_retrieve(query, user, domain, *, top=8):
        return list(fake_cockpit if domain.id == "cockpit" else fake_selfwiki)

    with patch.object(copilot, "retrieve", new=fake_retrieve), patch.object(
        copilot, "get_domain", new=lambda i: _Dom(i)
    ), patch.object(copilot, "_synthesize", new=AsyncMock(return_value="answer [1][2]")):
        out = await copilot.answer_question("q", user=None)

    assert out["answer"] == "answer [1][2]"
    # merged + globally reindexed 1..2; kb tag preserved
    assert [s["index"] for s in out["sources"]] == [1, 2]
    assert {s["kb"] for s in out["sources"]} == {"cockpit", "selfwiki"}


@pytest.mark.asyncio
async def test_answer_question_empty_retrieval_short_circuits():
    async def empty_retrieve(query, user, domain, *, top=8):
        return []

    synth = AsyncMock(return_value="should not be called")
    with patch.object(copilot, "retrieve", new=empty_retrieve), patch.object(
        copilot, "get_domain", new=lambda i: _Dom(i)
    ), patch.object(copilot, "_synthesize", new=synth):
        out = await copilot.answer_question("q", user=None)

    assert out["sources"] == []
    assert "Não encontrei" in out["answer"]
    synth.assert_not_awaited()
