"""Responses→AG-UI bridge for the hosted agent twins.

`last_user_text` was `_last_user_text`: private by name, imported by `grounded` anyway. Making
it public is the honest description of what it already was — a shared helper — and it is the
kind of leak the internal/public split exists to surface.
"""

from app.modules.hosted.internal.hosted import (
    _last_user_text as last_user_text,
    aclose,
    stream_agui,
    stream_platform_agui,
)

__all__ = ["aclose", "last_user_text", "stream_agui", "stream_platform_agui"]
