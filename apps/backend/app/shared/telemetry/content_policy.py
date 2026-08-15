"""What telemetry is allowed to carry (I-10).

Default is OFF. Prompts, model messages, tool arguments and retrieved documents never leave
the process unless someone deliberately sets `TELEMETRY_CAPTURE_CONTENT=true`, and even then
they go in span *events* with redaction — never in span attributes, which are indexed,
retained and hard to purge.

Two rules that hold regardless of the switch:
  - ACL-trimmed documents never enter telemetry with their content. The whole point of the
    per-document ACL (Rule #6) is that a caller sees only what they are entitled to; a trace
    is read by operators the ACL never checked.
  - Approver identity stays out. The HITL model records the approver's ROLE; the person
    belongs in the application's audit log, which has its own access rules.
"""

from __future__ import annotations

import re

MAX_VALUE_CHARS = 2000

# Anything that looks like a credential is redacted before any content is emitted. This is a
# backstop, not the control — the control is that capture is off by default.
_REDACTIONS = (
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "«aws-key»"),
    (re.compile(r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "«jwt»"),
    (re.compile(r"(?i)\b(api[-_ ]?key|secret|password|token)\b\s*[:=]\s*\S+"), r"\1=«redacted»"),
    (re.compile(r"\bBearer\s+\S+"), "Bearer «redacted»"),
)


def capture_enabled(settings) -> bool:
    """True only when content capture was explicitly switched on."""
    return bool(getattr(settings, "telemetry_capture_content", False))


def redact(text: str) -> str:
    """Strip credential-shaped substrings and cap the length."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    if len(text) > MAX_VALUE_CHARS:
        text = text[:MAX_VALUE_CHARS] + f"… «{len(text) - MAX_VALUE_CHARS} more chars»"
    return text
