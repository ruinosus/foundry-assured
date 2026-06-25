"use client";

// App shell. When Entra is configured, gates the chat behind an Entra ID sign-in
// and forwards the user's access token to the backend (which does the OBO
// exchange). When Entra is not configured, renders the chat directly (dev mode).

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import {
  MsalProvider,
  useIsAuthenticated,
  useMsal,
} from "@azure/msal-react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured, msalInstance } from "./auth/msal";

const WorkflowSteps = dynamic(
  () => import("./components/WorkflowSteps").then((m) => m.WorkflowSteps),
  { ssr: false },
);

function Chat({ authorization }: { authorization?: string }) {
  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={authorization ? { Authorization: authorization } : undefined}
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
        <WorkflowSteps />
        <div style={{ flex: 1, minHeight: 0 }} className="copilotkit-chat-host">
          <CopilotChat agentId="helpdesk" />
        </div>
      </main>
    </CopilotKitProvider>
  );
}

const center: React.CSSProperties = {
  display: "flex",
  height: "100vh",
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
    instance
      .acquireTokenSilent({ scopes: apiScopes, account: accounts[0] })
      .then((r) => setToken(r.accessToken))
      .catch(() => instance.acquireTokenRedirect({ scopes: apiScopes }));
  }, [isAuthenticated, accounts, instance]);

  if (!isAuthenticated) {
    return (
      <div style={center}>
        <p>Sign in to use the Helpdesk Concierge.</p>
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

function AuthedApp() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    msalInstance?.initialize().then(() => setReady(true));
  }, []);
  if (!ready || !msalInstance) return <div style={center}>Loading…</div>;
  return (
    <MsalProvider instance={msalInstance}>
      <AuthedChat />
    </MsalProvider>
  );
}

export default function HelpdeskApp() {
  // Module-constant branch (not a hook), so this early return is safe.
  if (!authConfigured) return <Chat />;
  return <AuthedApp />;
}
