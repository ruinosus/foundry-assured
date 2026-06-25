"use client";

// Phase 2: multi-agent workflow on CopilotKit v2.
// The v2 CopilotKitProvider honors `renderActivityMessages`, which the legacy
// <CopilotKit> provider ignored — that's why the executor steps never rendered.
// Each triage/retrieve/resolve step now renders inline as it runs, then the
// final grounded answer streams.

import { CopilotKitProvider, CopilotChat } from "@copilotkit/react-core/v2";
import { executorActivityRenderer } from "./components/ExecutorActivity";

export default function Page() {
  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
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
          <CopilotChat agentId="helpdesk" />
        </div>
      </main>
    </CopilotKitProvider>
  );
}
