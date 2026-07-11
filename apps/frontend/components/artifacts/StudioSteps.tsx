"use client";

// Tool-activity strip for the Studio canvas. Reads agent events directly (WorkflowSteps.tsx
// pattern), decoupled from the chat transcript and immune to the HITL non-terminal-status bug.
// PRIMARY source: the CUSTOM function_approval_request event carries update_artifact's inputs
// (title/type/skill) and always fires (it also drives the review bar) — same payload
// ArtifactStudio.onEvent already consumes. BONUS: TOOL_CALL_START names surface un-gated skill
// tools (load_skill, …). confirm_changes is never shown. Collapsible; collapsed by default.
import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";

type Gen = { title?: string; type?: string; skill?: string };

export function StudioSteps() {
  const { agent } = useAgent({ agentId: "artifacts-studio" });
  const [gen, setGen] = useState<Gen | null>(null); // from the guaranteed CUSTOM approval event
  const [tools, setTools] = useState<string[]>([]); // bonus: un-gated tool names, if they fire
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      // Keep `gen` across runs so the "generated" record stays visible after approval (a new
      // generation's CUSTOM event replaces it). Only reset the bonus tool list per run.
      onRunInitialized: () => { setTools([]); },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEvent: ({ event }: any) => {
        const t = event?.type;
        if (t === "CUSTOM" && (event?.name === "function_approval_request" || event?.name === "request_info")) {
          const fc = event.value?.function_call ?? {};
          let args: any = fc.arguments ?? {};
          if (typeof args === "string") { try { args = JSON.parse(args); } catch { args = {}; } }
          setGen({ title: args.title, type: args.type, skill: args.skill });
        } else if (t === "TOOL_CALL_START") {
          const name: string = event.toolCallName;
          if (name && name !== "confirm_changes" && name !== "update_artifact") {
            setTools((p) => (p.includes(name) ? p : [...p, name]));
          }
        }
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  const chips: React.ReactNode[] = [];
  if (gen?.skill) chips.push(<span key="skill" className="step-chip">🎨 <b>skill: {gen.skill}</b></span>);
  for (const name of tools) chips.push(<span key={`t-${name}`} className="step-chip">🎨 <b>{name}</b></span>);
  if (gen) {
    const detail = [gen.title, gen.type].filter(Boolean).join(" · ");
    chips.push(
      <span key="gen" className="step-chip"><b>generated the artifact</b>
        {detail ? <span className="muted"> · {detail}</span> : null}</span>,
    );
  }
  if (chips.length === 0) return null;

  return (
    <div data-testid="steps-strip" className="steps-strip">
      <button className="steps-summary" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span aria-hidden>{open ? "▾" : "▸"}</span> {chips.length} step{chips.length > 1 ? "s" : ""} ✓
      </button>
      {open && <div className="steps-list">{chips}</div>}
    </div>
  );
}
