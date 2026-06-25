"use client";

// Phase 2: multi-agent workflow on CopilotKit v2. The WorkflowSteps panel
// subscribes to the agent's events and lights up triage -> retrieve -> resolve
// as they run, marking them all done when the run finishes; the grounded answer
// streams in the chat below. Generative UI + approval cards (HITL) arrive in
// Phase 4.

import { CopilotKitProvider, CopilotChat } from "@copilotkit/react-core/v2";
import dynamic from "next/dynamic";

// Client-only: WorkflowSteps' useAgent subscription has no agent during SSR.
const WorkflowSteps = dynamic(
  () => import("./components/WorkflowSteps").then((m) => m.WorkflowSteps),
  { ssr: false },
);

export default function Page() {
  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit">
      <main
        style={{
          height: "100vh",
          display: "flex",
          flexDirection: "column",
          maxWidth: 768,
          margin: "0 auto",
        }}
      >
        <h1 style={{ padding: "16px 24px 8px", fontFamily: "system-ui" }}>
          Helpdesk Concierge
        </h1>
        <WorkflowSteps />
        <div style={{ flex: 1, minHeight: 0 }} className="copilotkit-chat-host">
          <CopilotChat agentId="helpdesk" />
        </div>
      </main>
    </CopilotKitProvider>
  );
}
