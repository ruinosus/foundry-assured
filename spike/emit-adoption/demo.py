"""PROTÓTIPO — build-emit ("Terraform") adoption demo for the foundry concierge.

WHAT THIS PROVES
================
The foundry today consumes DNA at RUNTIME: ``app/agents/prompts.py`` calls
``dna.load_prompts`` at import time and composes the concierge instructions in
the running process (the dna-sdk travels in the deploy).

The "Terraform" model is different: author in DNA, EMIT the runtime's native
artifact at BUILD time, and let the runtime load the NATIVE artifact — the
runtime never imports the dna-sdk.

This demo does exactly that for ``concierge-grounded``:

1. It loads ``spike/emit-adoption/concierge.agent.yaml`` — the artifact produced
   by ``dna emit concierge-grounded --target agent-framework`` — through the very
   same ``agent_framework_declarative.AgentFactory`` the foundry already uses to
   turn a declarative ``PromptAgent`` into a live ``agent_framework.Agent``.
2. It asserts the loaded agent's instructions are BYTE-EQUAL to what the DNA
   scope composes at runtime via ``dna.load_prompts`` — the two models produce
   the identical prompt. (This step needs the dna-sdk ONLY as an oracle for the
   comparison; the build-emit runtime path in step 1 does not.)

.NET / Azure GATE
=================
The emitted PromptAgent carries no ``model:`` block (the DNA agent leaves the
model unbound — Genome default), so ``AgentFactory`` uses a caller-supplied
chat ``client`` and never resolves a Foundry/Azure provider or a .NET runtime.
We inject a tiny stub ``SupportsChatGetResponse`` so the agent constructs fully
offline. If you WANT the real FoundryChatClient path (needs Azure creds +
possibly ``DOTNET_ROLL_FORWARD=Major``), emit with ``--model`` and drop the stub.

Run:  <backend-venv>/bin/python spike/emit-adoption/demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE / "concierge.agent.yaml"
# The foundry's baked DNA scope — the SAME scope prompts.py composes from.
DNA_BASE_DIR = HERE.parents[1] / "apps" / "backend" / ".dna"
DNA_SCOPE = "helpdesk"
AGENT = "concierge-grounded"


class _StubChatClient:
    """Minimal ``SupportsChatGetResponse`` so the Agent builds with no cloud.

    We are proving artifact LOADING + instruction fidelity, not model calls, so
    the client only needs to exist and satisfy the protocol shape. A real
    deployment passes ``FoundryChatClient`` (what the foundry uses today) or lets
    the emitted ``model:`` block resolve the provider.
    """

    async def get_response(self, *args, **kwargs):  # pragma: no cover - never called here
        raise RuntimeError("stub client — the demo does not invoke the model")


def _agent_instructions(agent) -> str:
    """agent-framework stashes the PromptAgent instructions in default_options.

    ``Agent(instructions=...)`` folds into ``default_options`` (a dict here, or a
    ChatOptions object depending on version) — read it back defensively.
    """
    opts = getattr(agent, "default_options", None)
    if isinstance(opts, dict):
        val = opts.get("instructions")
    else:
        val = getattr(opts, "instructions", None)
    if val is None:
        raise AssertionError("could not locate instructions on the loaded Agent")
    return val


def _read_emitted() -> dict:
    if not ARTIFACT.exists():
        sys.exit(
            f"ERROR: {ARTIFACT} not found. Emit it first:\n"
            f"  DNA_BASE_DIR={DNA_BASE_DIR} dna emit {AGENT} "
            f"--target agent-framework --scope {DNA_SCOPE} --out {ARTIFACT}"
        )
    return yaml.safe_load(ARTIFACT.read_text())


def main() -> int:
    print("=" * 72)
    print("PROTÓTIPO — build-emit (Terraform) adoption: concierge-grounded")
    print("=" * 72)

    emitted = _read_emitted()
    print(f"\n[1] Emitted native artifact: {ARTIFACT.name}")
    print(f"    kind={emitted.get('kind')!r}  name={emitted.get('name')!r}")
    print(f"    has model block? {'model' in emitted}  (unbound → stub client)")

    # --- BUILD-EMIT runtime path: load the NATIVE artifact, no dna-sdk ---------
    try:
        from agent_framework_declarative import AgentFactory
    except ModuleNotFoundError:
        print(
            "\n[SKIP] agent_framework_declarative not importable in this interpreter.\n"
            "       Run with the backend venv:\n"
            "         apps/backend/.venv/bin/python spike/emit-adoption/demo.py\n"
            "       Falling back to STRUCTURAL validation + byte-equal only."
        )
        return _structural_only(emitted)

    factory = AgentFactory(client=_StubChatClient())
    agent = factory.create_agent_from_yaml_path(str(ARTIFACT))
    loaded_instr = _agent_instructions(agent)
    print("\n[2] Loaded via agent_framework_declarative.AgentFactory")
    print(f"    -> live object: {type(agent).__module__}.{type(agent).__name__}")
    print(f"    -> agent.name = {agent.name!r}")
    print(f"    -> instructions length = {len(loaded_instr)} chars")

    # --- PRIMARY GATE: the live Agent's prompt == the emitted artifact ---------
    # This is the RUNTIME-side link and needs NO dna-sdk: the agent-framework
    # loader carried the emitted `instructions` verbatim into a live Agent.
    ok = loaded_instr == emitted["instructions"]
    print("\n[3] BYTE-EQUAL GATE — runtime link  (live Agent  ==  emitted YAML)")
    print(f"    -> {'PASS ✅' if ok else 'FAIL ❌'}  ({len(loaded_instr)} chars)")
    if not ok:
        _diff(loaded_instr, emitted["instructions"])
        return 1

    # --- SECOND LINK (best effort): emitted == what load_prompts composes ------
    # Closes the transitive chain load_prompts == emitted == live Agent. Needs a
    # dna-sdk that exports load_prompts; if this interpreter's dna is a different
    # pin (the backend runtime need not carry the composer), we say so honestly
    # and note that the dna venv proves this link (`_lib`/build side).
    _oracle_link(emitted["instructions"])

    print("\nRESULT: the agent-framework Agent built from the EMITTED native YAML")
    print("        carries the byte-identical prompt — and THIS load path imported")
    print("        NO dna-sdk (the runtime depends only on the native artifact).")
    return 0


def _oracle_link(emitted_instr: str) -> None:
    """Best-effort: emitted instructions == dna.load_prompts (the build side)."""
    try:
        from dna import load_prompts  # type: ignore
    except (ImportError, ModuleNotFoundError):
        print("\n[4] BUILD-side link (emitted == dna.load_prompts): SKIPPED here —")
        print("    this interpreter's `dna` does not export load_prompts (runtime")
        print("    need not carry the composer). Proven under the dna venv:")
        print("      .venv-dna/bin/python spike/emit-adoption/demo.py")
        return
    composed = load_prompts(DNA_SCOPE, base_dir=str(DNA_BASE_DIR))[AGENT]
    ok = emitted_instr == composed
    print("\n[4] BYTE-EQUAL GATE — build link  (emitted YAML  ==  dna.load_prompts)")
    print(f"    -> {'PASS ✅' if ok else 'FAIL ❌'}  ({len(composed)} chars)")
    if not ok:
        _diff(emitted_instr, composed)


def _structural_only(emitted: dict) -> int:
    """No agent-framework available (e.g. the dna venv): validate shape + build link."""
    assert emitted.get("kind") == "Prompt", "emitted artifact must be kind: Prompt"
    assert emitted.get("instructions"), "emitted artifact must carry instructions"
    print("\n[structural] kind == 'Prompt' and instructions present: OK ✅")
    from dna import load_prompts

    composed = load_prompts(DNA_SCOPE, base_dir=str(DNA_BASE_DIR))[AGENT]
    ok = emitted["instructions"] == composed
    print("[byte-equal] BUILD link  (emitted YAML  ==  dna.load_prompts)")
    print(f"    -> {'PASS ✅' if ok else 'FAIL ❌'}  ({len(composed)} chars)")
    if not ok:
        _diff(emitted["instructions"], composed)
        return 1
    print("\nRESULT: the emitted native artifact is byte-equal to the runtime-")
    print("        composed prompt. (agent-framework absent here → structural path;")
    print("        run the backend venv for the live-Agent load link.)")
    return 0


def _diff(a: str, b: str) -> None:
    import difflib

    for line in difflib.unified_diff(
        a.splitlines(), b.splitlines(), "loaded", "composed", lineterm=""
    ):
        print("   " + line)


if __name__ == "__main__":
    raise SystemExit(main())
