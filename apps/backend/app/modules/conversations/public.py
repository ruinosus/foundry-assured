"""Superfície do módulo de conversas. Único ponto importável de fora (ADR-017)."""

from __future__ import annotations

from app.modules.conversations.internal.langchain_recording import usage_callback
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
from app.modules.conversations.internal.recorder import (
    bind_conversation,
    bind_dependency,
    current_conversation,
    usage_recorder,
)
from app.modules.conversations.internal.store import conversation_user

__all__ = [
    "StoredHistoryProvider",
    "bind_conversation",
    "bind_dependency",
    "build_history_provider",
    "conversation_user",
    "current_conversation",
    "find_conversation",
    "get_conversation",
    "list_conversations",
    "record_turn",
    "record_usage",
    "usage_callback",
    "usage_recorder",
    "usage_totals",
]
