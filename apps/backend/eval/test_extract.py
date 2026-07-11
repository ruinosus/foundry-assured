"""Unit tests for the Meeting Board node extractor (mock _responses → offline-safe)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services import copilot


@pytest.mark.asyncio
async def test_extract_parses_valid_json():
    payload = '{"nodes":[{"type":"pergunta","label":"failover?","detail":"como faz o failover"}],"edges":[],"suggestedQuestion":"volume?"}'
    with patch.object(copilot, "_responses", new=AsyncMock(return_value=payload)):
        out = await copilot.extract_nodes([{"speaker": "SPEAKER_01", "text": "e o failover?"}], [], user=None)
    assert out["nodes"][0]["type"] == "pergunta"
    assert out["nodes"][0]["label"] == "failover?"
    assert out["edges"] == []
    assert out["suggestedQuestion"] == "volume?"


@pytest.mark.asyncio
async def test_extract_failsoft_on_bad_json():
    with patch.object(copilot, "_responses", new=AsyncMock(return_value="desculpa, não consegui")):
        out = await copilot.extract_nodes([{"speaker": "me", "text": "oi"}], [], user=None)
    assert out == {"nodes": [], "edges": [], "suggestedQuestion": None}


@pytest.mark.asyncio
async def test_extract_drops_invalid_node_types():
    payload = '{"nodes":[{"type":"kb","label":"x"},{"type":"topico","label":"multi-tenant"}],"edges":[]}'
    with patch.object(copilot, "_responses", new=AsyncMock(return_value=payload)):
        out = await copilot.extract_nodes([{"speaker": "me", "text": "..."}], [], user=None)
    labels = [n["label"] for n in out["nodes"]]
    assert labels == ["multi-tenant"]  # 'kb' type dropped (KB is click-only)


@pytest.mark.asyncio
async def test_extract_strips_json_fences():
    payload = '```json\n{"nodes":[{"type":"ideia","label":"piloto 30d"}],"edges":[]}\n```'
    with patch.object(copilot, "_responses", new=AsyncMock(return_value=payload)):
        out = await copilot.extract_nodes([{"speaker": "me", "text": "..."}], [], user=None)
    assert out["nodes"][0]["label"] == "piloto 30d"
