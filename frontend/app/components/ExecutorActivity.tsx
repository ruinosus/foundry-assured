"use client";

// Renders each workflow executor step inline as it runs. Registered via the v2
// CopilotKitProvider's `renderActivityMessages` (the v1 <CopilotKit> provider
// ignores it, which is why earlier attempts showed nothing).
//
// The AG-UI workflow emits one activity per executor (activityType "executor",
// content { executor_id, status: in_progress|completed }).

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

// Minimal Standard Schema (passthrough) — the renderer's `content` field expects
// a StandardSchemaV1; this returns the payload untouched so we avoid pulling zod.
const passthroughSchema = {
  "~standard": {
    version: 1 as const,
    vendor: "foundry-helpdesk",
    validate: (value: unknown) => ({ value }),
  },
};

function StepCard({ content }: { content: ExecutorContent }) {
  const meta = STEP_META[content.executor_id] ?? { label: content.executor_id, desc: "" };
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
      <span aria-hidden style={{ fontSize: 14, color }}>
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
