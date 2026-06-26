"use client";

// App shell. When Entra is configured, gates the chat behind an Entra ID sign-in
// and forwards the user's access token to the backend (which does the OBO
// exchange). When Entra is not configured, renders the chat directly (dev mode).

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { TicketApproval } from "@/components/chat/TicketApproval";

const WorkflowSteps = dynamic(
  () => import("@/components/chat/WorkflowSteps").then((m) => m.WorkflowSteps),
  { ssr: false },
);

function Chat({ authorization }: { authorization?: string }) {
  // Engine selector: the live AG-UI workflow (steps/HITL/OBO/memory) vs the Phase 6
  // Foundry hosted agent (managed, Responses protocol). Same agent, two delivery
  // models — the showcase shows both without losing the rich experience.
  const [mode, setMode] = useState<"live" | "hosted">("live");

  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={authorization ? { Authorization: authorization } : undefined}
      // Renders the CopilotKit Inspector (the floating devtools icon) with the
      // live core wired up. Setting showDevConsole is the supported way — a bare
      // <CopilotKitInspector/> has no core and shows "core not attached".
      // Dev-only: NODE_ENV is inlined at build, so production bundles ship without it.
      showDevConsole={process.env.NODE_ENV !== "production"}
    >
      <main
        style={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          maxWidth: 820,
          width: "100%",
          margin: "0 auto",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 4px" }}>
          <div className="seg">
            <button className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>
              Live workflow
            </button>
            <button className={mode === "hosted" ? "on" : ""} onClick={() => setMode("hosted")}>
              Hosted agent
            </button>
          </div>
          <span className="muted" style={{ fontSize: 12 }}>
            {mode === "live"
              ? "AG-UI · live steps, approval, per-user OBO + memory"
              : "Foundry Agent Service · managed, Responses protocol"}
          </span>
        </div>

        {mode === "live" ? (
          <>
            <WorkflowSteps />
            <TicketApproval />
            <div style={{ flex: 1, minHeight: 0 }} className="copilotkit-chat-host">
              <CopilotChat agentId="helpdesk" />
            </div>
          </>
        ) : (
          // Hosted agent rendered through the same CopilotChat, via the AG-UI
          // bridge (backend /helpdesk-hosted). Streams, but no steps/approval.
          <div style={{ flex: 1, minHeight: 0 }} className="copilotkit-chat-host">
            <CopilotChat agentId="helpdesk-hosted" />
          </div>
        )}
      </main>
    </CopilotKitProvider>
  );
}

const center: React.CSSProperties = {
  display: "flex",
  height: "100%",
  minHeight: 360,
  alignItems: "center",
  justifyContent: "center",
  fontFamily: "system-ui",
  flexDirection: "column",
  gap: 16,
};

function AuthedChat() {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accounts[0]) return;
    let active = true;
    const acquire = () =>
      instance
        .acquireTokenSilent({ scopes: apiScopes, account: accounts[0] })
        .then((r) => {
          if (active) setToken(r.accessToken);
        })
        .catch(() => instance.acquireTokenRedirect({ scopes: apiScopes }));
    acquire();
    // Refresh well before the ~1h access-token expiry, otherwise the live (OBO)
    // chat silently starts returning 401 mid-session and "stops responding".
    const id = setInterval(acquire, 4 * 60 * 1000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [isAuthenticated, accounts, instance]);

  if (!isAuthenticated) {
    return (
      <div style={center}>
        <p>Sign in to use {branding.product}.</p>
        <button
          onClick={() => instance.loginRedirect({ scopes: apiScopes })}
          style={{
            padding: "10px 16px",
            borderRadius: 8,
            border: "1px solid #2563eb",
            background: "#2563eb",
            color: "white",
            cursor: "pointer",
            fontSize: 14,
          }}
        >
          Sign in with Microsoft
        </button>
      </div>
    );
  }
  if (!token) return <div style={center}>Acquiring token…</div>;
  return <Chat authorization={`Bearer ${token}`} />;
}

export default function HelpdeskApp() {
  // MSAL is initialized app-wide by the root <Providers>; here we only gate the
  // chat behind sign-in. Module-constant branch (not a hook), so the early
  // return is safe.
  if (!authConfigured) return <Chat />;
  return <AuthedChat />;
}
