"use client";

// Renders each workflow executor step inline in the chat as it runs.
//
// The AG-UI workflow emits ACTIVITY_SNAPSHOT events (activityType "executor")
// with { executor_id, status } — one per triage/retrieve/resolve, updating from
// "in_progress" to "completed". We register a ReactActivityMessageRenderer for
// activityType "executor" (CopilotKit v2's documented API) so these render live.
//
// Verified against the captured AG-UI event stream + @copilotkit/react-core
// types (renderActivityMessages on <CopilotKit>). The renderer interface isn't
// exported by name, so we build the object structurally.

type ExecutorContent = {
  executor_id: string;
  status: string;
  data?: unknown;
};

const STEP_META: Record<string, { label: string; desc: string }> = {
  triage: { label: "Triage", desc: "Classifying intent & urgency" },
  retrieve: { label: "Retrieve", desc: "Searching the runbook knowledge base" },
  resolve: { label: "Resolve", desc: "Writing the grounded, cited answer" },
};

// Minimal Standard Schema (passthrough) so we don't need to pull in zod just to
// satisfy the renderer's `content` field — it returns the payload untouched.
const passthroughSchema = {
  "~standard": {
    version: 1 as const,
    vendor: "foundry-helpdesk",
    validate: (value: unknown) => ({ value }),
  },
};

function StepCard({ content }: { content: ExecutorContent }) {
  const meta = STEP_META[content.executor_id] ?? {
    label: content.executor_id,
    desc: "",
  };
  const done = content.status === "completed";
  const color = done ? "#16a34a" : "#2563eb";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 12px",
        margin: "4px 0",
        border: `1px solid ${color}33`,
        borderLeft: `3px solid ${color}`,
        borderRadius: 8,
        background: done ? "#f0fdf4" : "#eff6ff",
        fontFamily: "system-ui",
      }}
    >
      <span aria-hidden style={{ fontSize: 14 }}>
        {done ? "✓" : "●"}
      </span>
      <span style={{ fontSize: 13, fontWeight: 600 }}>{meta.label}</span>
      <span style={{ fontSize: 12, color: "#64748b" }}>
        {done ? meta.desc.replace(/ing\b/, "ed") : `${meta.desc}…`}
      </span>
    </div>
  );
}

export const executorActivityRenderer = {
  activityType: "executor",
  content: passthroughSchema,
  render: ({ content }: { content: ExecutorContent }) => <StepCard content={content} />,
};
