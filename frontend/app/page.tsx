"use client";

// Phase 2: multi-agent workflow. The WorkflowSteps panel reads the per-executor
// activity messages and lights up triage -> retrieve -> resolve as they run;
// the final grounded answer streams in the chat. Generative UI + approval cards
// for HITL arrive in Phase 4.

import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { WorkflowSteps } from "./components/WorkflowSteps";

export default function Page() {
  return (
    <CopilotKit runtimeUrl="/api/copilotkit" agent="helpdesk">
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
          <CopilotChat
            labels={{
              title: "Helpdesk Concierge",
              initial: "Hi! Ask me an engineering support question.",
            }}
          />
        </div>
      </main>
    </CopilotKit>
  );
}
