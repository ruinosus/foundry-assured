"use client";

// TechDocs expert chat — a second domain alongside the helpdesk. Grounded Q&A over the
// TechDocs knowledge base (backend /techdocs, agentId "techdocs"). Same Entra sign-in +
// token forwarding as the concierge; no Live/Hosted toggle, steps, or HITL (the TechDocs
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
        <div >
          <span className="muted t-xs">
            TechDocs expert · grounded in the TechDocs platform knowledge base (cites the
            component + doc)
          </span>
        </div>
        <div className="fill copilotkit-chat-host">
          <CopilotChat agentId="techdocs" />
        </div>
      </main>
    </CopilotKitProvider>
  );
}


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

  if (!token) return <div className="console-center">Acquiring token…</div>;
  return <Chat authorization={`Bearer ${token}`} />;
}

export default function TechDocsApp() {
  if (!authConfigured) return <Chat />;
  return <AuthedChat />;
}
