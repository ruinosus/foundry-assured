"""GenAI semantic-convention names, pinned in ONE file (ADR-017, spec §2.6).

The OpenTelemetry GenAI semantic conventions are pre-1.0 and still renaming things. Every
`gen_ai.*` string in this backend comes from here, so a convention migration is a diff in one
file instead of a grep across the codebase. **Never write a `gen_ai.*` literal elsewhere** —
that is a red gate in the spec.

Pinned against: opentelemetry-semantic-conventions GenAI, as emitted by agent-framework 1.14.0
(`enable_instrumentation`). The framework emits the `gen_ai.*` set itself; the `app.*` set is
this repository's own and is not governed by any upstream spec.
"""

from __future__ import annotations

# --- Upstream GenAI conventions (pre-1.0 — expect renames) ---------------------------
GEN_AI_OPERATION = "gen_ai.operation.name"
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"

# Operation values, used to name spans as "{operation} {model}".
OP_INVOKE_AGENT = "invoke_agent"
OP_CHAT = "chat"
OP_EXECUTE_TOOL = "execute_tool"

# --- This repository's own attributes -------------------------------------------------
# `app.module` deliberately mirrors the import-linter boundaries, so a dashboard slices the
# system along the same lines CI enforces.
APP_DOMAIN = "app.domain"
APP_MODULE = "app.module"
APP_TENANT_ID = "app.tenant_id"
APP_DEPLOYMENT_MODE = "app.deployment_mode"
APP_RUN_OUTCOME = "app.run.outcome"

# Approval (HITL). The events themselves are emitted in Phase 5.5b; the names are pinned here
# now so the two phases cannot disagree about them.
APPROVAL_REQUESTED = "approval.requested"
APPROVAL_GRANTED = "approval.granted"
APPROVAL_REJECTED = "approval.rejected"
APPROVAL_ACTION = "approval.action"
APPROVAL_ATTEMPT = "approval.attempt"
APPROVAL_REQUIRED_ROLE = "approval.required_role"
APPROVAL_APPROVER_ROLE = "approval.approver_role"

GUARDRAIL_DECLINE = "guardrail.decline"


def span_name(operation: str, model: str | None = None) -> str:
    """The convention's span naming: `{operation} {model}`, or just the operation."""
    return f"{operation} {model}" if model else operation
