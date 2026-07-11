"use client";

// Cockpit expert chat — a second domain alongside the helpdesk. Grounded Q&A over the
// Cockpit knowledge base (backend /cockpit, agentId "cockpit"). Same Entra sign-in +
// token forwarding as the concierge; no Live/Hosted toggle, steps, or HITL (the Cockpit
// agent is pure reference retrieval).

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";

function Chat({ authorization }: { authorization?: string }) {
  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={authorization ? { Authorization: authorization } : undefined}
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
        <div style={{ padding: "12px 4px" }}>
          <span className="muted" style={{ fontSize: 12 }}>
            Cockpit expert · grounded in the Cockpit platform knowledge base (cites the
            component + doc)
          </span>
        </div>
        <div style={{ flex: 1, minHeight: 0 }} className="copilotkit-chat-host">
          <CopilotChat agentId="cockpit" />
        </div>
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
    const id = setInterval(acquire, 4 * 60 * 1000); // refresh before the ~1h expiry
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [isAuthenticated, accounts, instance]);

  if (!token) return <div style={center}>Acquiring token…</div>;
  return <Chat authorization={`Bearer ${token}`} />;
}

export default function CockpitApp() {
  if (!authConfigured) return <Chat />;
  return <AuthedChat />;
}
