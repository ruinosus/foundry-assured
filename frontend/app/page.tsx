"use client";

// Phase 2: multi-agent workflow with the steps rendered inline as they run.
// The executor activity renderer turns each triage/retrieve/resolve step into a
// live card in the chat (in_progress -> completed), then the final answer
// streams. Generative UI + approval cards for HITL arrive in Phase 4.

import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { executorActivityRenderer } from "./components/ExecutorActivity";

export default function Page() {
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="helpdesk"
      renderActivityMessages={[executorActivityRenderer] as never}
    >
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
