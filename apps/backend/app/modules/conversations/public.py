"""Superfície do módulo de conversas. Único ponto importável de fora (ADR-017)."""

from __future__ import annotations

from app.modules.conversations.internal.listing import (
    find_conversation,
    get_conversation,
    list_conversations,
    record_turn,
    record_usage,
    usage_totals,
)
from app.modules.conversations.internal.provider import (
    StoredHistoryProvider,
    build_history_provider,
)
from app.modules.conversations.internal.store import conversation_user

__all__ = [
    "StoredHistoryProvider",
    "build_history_provider",
    "conversation_user",
    "find_conversation",
    "get_conversation",
    "list_conversations",
    "record_turn",
    "record_usage",
    "usage_totals",
]
