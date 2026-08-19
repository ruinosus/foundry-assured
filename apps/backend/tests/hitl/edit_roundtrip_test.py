"""`EditDecision` round-trips: the human's correction is what the tool executes.

ADR-019 adopted LangChain's HITL because `edit` is a product requirement — the approver must
be able to CORRECT an action before approving it, not only accept or refuse. The Agent
Framework offers a boolean.

The ADR also warned that a type signature promising `edit` is not `edit` working end to end,
especially since `opentag-reference` HAS `interrupt_on` and does not use it. This started as
that spike and stayed as a test, because the guarantee it proves is the reason a second agent
runtime was taken on at all. If this goes red, the decision behind it is void.

Offline and deterministic — no model, no network:

  1. an agent proposes a tool call with WRONG arguments
  2. the middleware interrupts
  3. we answer with an EditDecision carrying corrected arguments
  4. the tool executes with the CORRECTED arguments, and we prove it

If step 4 fails, ADR-019 needs revisiting.

    uv run python -m tests.hitl.edit_roundtrip_test
"""

from __future__ import annotations

import sys

from langchain.agents import create_agent
from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

# What the tool actually received — the only evidence that matters.
RECEIVED: list[dict] = []


@tool
def open_ticket(summary: str, priority: str) -> str:
    """Open a support ticket."""
    RECEIVED.append({"summary": summary, "priority": priority})
    return f"ticket opened: {summary} ({priority})"


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # A fake model that proposes ONE tool call with a summary we will correct.
    wrong = AIMessage(
        content="",
        tool_calls=[{
            "name": "open_ticket",
            "args": {"summary": "pod crashloop", "priority": "low"},
            "id": "call-1",
            "type": "tool_call",
        }],
    )
    class _ToolCapableFake(GenericFakeChatModel):
        """GenericFakeChatModel with bind_tools — the core fakes do not implement it, and the
        agent factory calls it unconditionally. Binding is a no-op: this spike tests the
        approval round-trip, not tool selection."""

        def bind_tools(self, tools, **kwargs):
            return self

    model = _ToolCapableFake(messages=iter([wrong, AIMessage(content="done")]))

    agent = create_agent(
        model=model,
        tools=[open_ticket],
        middleware=[HumanInTheLoopMiddleware(
            interrupt_on={"open_ticket": {"allowed_decisions": ["approve", "edit", "reject"]}}
        )],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "spike-1"}}

    # --- 1. run until the interrupt --------------------------------------------------------
    result = agent.invoke({"messages": [("user", "open a ticket")]}, config)
    interrupts = result.get("__interrupt__") or []
    check("the run interrupted instead of executing", len(interrupts) == 1)
    if not interrupts:
        print("\n❌ no interrupt — the rest cannot be tested.")
        return 1

    payload = interrupts[0].value
    print(f"      interrupt payload keys: {sorted(payload)}")
    reqs = payload.get("action_requests") or []
    check("the interrupt carries the proposed action", len(reqs) == 1)
    if reqs:
        print(f"      proposed: {reqs[0].get('action')} {reqs[0].get('args')}")

    check("nothing executed while waiting for the human", RECEIVED == [])

    # --- 2. answer with an EDIT, correcting both arguments ---------------------------------
    corrected = {"summary": "Kubernetes pod in CrashLoopBackOff", "priority": "high"}
    agent.invoke(
        Command(resume={"decisions": [{
            "type": "edit",
            "edited_action": {"name": "open_ticket", "args": corrected},
        }]}),
        config,
    )

    # --- 3. the evidence -------------------------------------------------------------------
    check("the tool executed exactly once", len(RECEIVED) == 1)
    if RECEIVED:
        print(f"      tool received: {RECEIVED[0]}")
        check("the tool got the CORRECTED summary, not the proposed one",
              RECEIVED[0].get("summary") == corrected["summary"])
        check("the tool got the CORRECTED priority", RECEIVED[0].get("priority") == corrected["priority"])

    if failures:
        print(f"\n❌ {len(failures)} check(s) failed — ADR-019 needs revisiting.")
        return 1
    print("\n✅ edit round-trips: the human's correction is what the tool executed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
