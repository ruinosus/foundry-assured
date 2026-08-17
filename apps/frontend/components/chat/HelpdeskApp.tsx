"use client";

// App shell. When Entra is configured, gates the chat behind an Entra ID sign-in
// and forwards the user's access token to the backend (which does the OBO
// exchange). When Entra is not configured, renders the chat directly (dev mode).

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { demoMode } from "@/lib/demo";
import { TicketApproval } from "@/components/chat/TicketApproval";

const WorkflowSteps = dynamic(
  () => import("@/components/chat/WorkflowSteps").then((m) => m.WorkflowSteps),
  { ssr: false },
);

function Chat({ authorization }: { authorization?: string }) {
  const locale = useLocale();
  // Engine selector: the live AG-UI workflow (steps/HITL/OBO/memory) vs the Phase 6
  // Foundry hosted agent (managed, Responses protocol). Same agent, two delivery
  // models — the showcase shows both without losing the rich experience.
  const [mode, setMode] = useState<"live" | "hosted">("live");

  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      // O chat sai do SERVIDOR Next para o backend, então o Accept-Language do navegador não
      // é repassado sozinho. `useLocale()` já é o idioma efetivo (escolha explícita ou o que o
      // navegador pediu), e mandá-lo aqui é o que faz o AGENTE responder na língua da tela.
      headers={{
        ...(authorization ? { Authorization: authorization } : {}),
        "Accept-Language": locale,
      }}
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
        <div className="row">
          {demoMode ? (
            // Demo mode talks to a recorded aimock fixture — only the Live AG-UI path
            // is replayed, so hide the engine toggle and flag that it's mocked.
            <span className="pill t-xs">
              ● Demo · replayed fixture, no Azure
            </span>
          ) : (
            <>
              <div className="seg">
                <button className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>
                  Live workflow
                </button>
                <button className={mode === "hosted" ? "on" : ""} onClick={() => setMode("hosted")}>
                  Hosted agent
                </button>
              </div>
              <span className="muted t-xs">
                {mode === "live"
                  ? "AG-UI · live steps, approval, per-user OBO + memory"
                  : "Foundry Agent Service · managed, Responses protocol"}
              </span>
            </>
          )}
        </div>

        {mode === "live" ? (
          <>
            <WorkflowSteps />
            <TicketApproval agentId="helpdesk" />
            <div className="fill copilotkit-chat-host">
              <CopilotChat agentId="helpdesk" />
            </div>
          </>
        ) : (
          // Hosted agent rendered through the same CopilotChat, via the AG-UI
          // bridge (backend /helpdesk-hosted). Streams, but no steps/approval.
          <div className="fill copilotkit-chat-host">
            <CopilotChat agentId="helpdesk-hosted" />
          </div>
        )}
      </main>
    </CopilotKitProvider>
  );
}


function AuthedChat() {
  const tc = useTranslations("common");
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
      <div className="console-center">
        <p>Sign in to use {branding.product}.</p>
        <button
          onClick={() => instance.loginRedirect({ scopes: apiScopes })}
          className="btn btn-primary"
        >
          Sign in with Microsoft
        </button>
      </div>
    );
  }
  if (!token) return <div className="console-center">{tc("acquiringToken")}</div>;
  return <Chat authorization={`Bearer ${token}`} />;
}

export default function HelpdeskApp() {
  const locale = useLocale();
  // MSAL is initialized app-wide by the root <Providers>; here we only gate the
  // chat behind sign-in. Module-constant branch (not a hook), so the early
  // return is safe.
  if (!authConfigured) return <Chat />;
  return <AuthedChat />;
}
