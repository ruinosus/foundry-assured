"""Defense-in-depth HTML validation.

The PRIMARY isolation boundary is the frontend iframe sandbox (opaque origin,
no allow-same-origin). This validation is a secondary gate: it enforces a size
cap and a minimal "looks like HTML" shape. It deliberately does NOT strip
<script> — the sandbox contains it, and stripping would break legitimate
AI-generated interactive artifacts.
"""
from __future__ import annotations

import re

_HTML_HINT = re.compile(r"<\s*(!doctype\s+html|html|body|div|section)\b", re.IGNORECASE)


class ValidationError(ValueError):
    pass


def validate_html(html: str, *, max_bytes: int) -> str:
    if not html or not html.strip():
        raise ValidationError("empty artifact")
    if len(html.encode("utf-8")) > max_bytes:
        raise ValidationError(f"artifact exceeds {max_bytes} bytes")
    if not _HTML_HINT.search(html):
        raise ValidationError("content does not look like HTML")
    return html
