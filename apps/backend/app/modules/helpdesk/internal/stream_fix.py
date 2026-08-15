"""Workaround for an agent-framework-ag-ui 1.0.0rc5 stream-ordering bug.

When a workflow's terminal output is a ``yield_output(text)`` — our
EscalationExecutor emits the resolved answer / ticket confirmation that way — the
adapter's terminal ``status`` branch emits RUN_FINISHED *before* draining the
open assistant text message (it drains only afterward, in the post-loop cleanup).
The AG-UI verifier in the CopilotKit runtime then rejects the whole stream:

    Cannot send 'RUN_FINISHED' while text messages are still active: <id>

Verified by reading ``agent_framework_ag_ui/_workflow_run.py``: the
``superstep_started`` / ``executor_invoked`` / ``request_info`` branches each call
``_drain_open_message()`` first, but the terminal ``status`` branch does not.

We wrap ``AgentFrameworkWorkflow.run`` and post-process its event stream to:

1. Re-order so every open text message is closed (TEXT_MESSAGE_END) before any
   terminal event, then drop the now-duplicate END the adapter emits in its
   post-loop drain.
2. Suppress the ``request_info`` TOOL_CALL events. The adapter emits the workflow
   interrupt BOTH as a tool call (start/args/end) AND as a CUSTOM ``request_info``
   event. We drive the approval card off the CUSTOM event, but CopilotChat renders
   the tool call as a "running" spinner that never resolves (no TOOL_CALL_RESULT
   on resume). Dropping the tool-call events removes the stuck indicator; the
   CUSTOM event and the RUN_FINISHED ``interrupt`` (used for resume) are untouched.

The wrapper sits downstream of the parent ``run()``, which calls
``snapshot_builder.observe(event)`` on the ORIGINAL events before yielding — so
suppression here never affects snapshot/replay persistence. Pure pass-through for
everything else, so it's a no-op once these are fixed upstream.
"""

from collections.abc import AsyncGenerator
from typing import Any

from ag_ui.core import (
    BaseEvent,
    RunErrorEvent,
    RunFinishedEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from agent_framework_ag_ui import AgentFrameworkWorkflow

_REQUEST_INFO_TOOL = "request_info"


class OrderedAgentFrameworkWorkflow(AgentFrameworkWorkflow):
    """AgentFrameworkWorkflow that fixes terminal ordering + the stuck interrupt tool call."""

    async def run(self, input_data: dict[str, Any]) -> AsyncGenerator[BaseEvent]:
        open_ids: set[str] = set()
        suppressed_tool_ids: set[str] = set()
        async for event in super().run(input_data):
            # Drop the request_info tool-call trio (start/args/end) — its id is
            # tracked from the start so the args/end (which carry only the id) go too.
            if isinstance(event, ToolCallStartEvent):
                if event.tool_call_name == _REQUEST_INFO_TOOL:
                    suppressed_tool_ids.add(event.tool_call_id)
                    continue
            elif isinstance(event, (ToolCallArgsEvent, ToolCallEndEvent)):
                if event.tool_call_id in suppressed_tool_ids:
                    if isinstance(event, ToolCallEndEvent):
                        suppressed_tool_ids.discard(event.tool_call_id)
                    continue

            if isinstance(event, TextMessageStartEvent):
                open_ids.add(event.message_id)
                yield event
                continue
            if isinstance(event, TextMessageEndEvent):
                # Suppress a duplicate END for a message we already closed early.
                if event.message_id in open_ids:
                    open_ids.discard(event.message_id)
                    yield event
                continue
            if isinstance(event, (RunFinishedEvent, RunErrorEvent)) and open_ids:
                # Close every still-open message before the terminal event.
                for message_id in list(open_ids):
                    yield TextMessageEndEvent(message_id=message_id)
                open_ids.clear()
                yield event
                continue
            yield event
