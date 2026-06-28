"use client";

// Assurance Console — the unified, config-driven surface for any domain agent.
//
// Two panes inside the (flush) shell: the chat (center) and the EvidencePanel (right,
// the citation/assurance signature). The AppShell sidebar is the domain switcher, so
// this is the same console for every domain — one route (/d/[domain]) drives all of them
// off lib/domains.ts. Workflow domains (helpdesk) additionally render the live steps +
// HITL approval; grounded domains are pure cited Q&A.
//
// Auth mirrors HelpdeskApp/CockpitApp: when Entra is configured we gate on sign-in and
// forward the user's access token (the backend does the OBO exchange); otherwise the
// chat renders directly (dev/demo mode).

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { getDomain, type Domain } from "@/lib/domains";
import { TicketApproval } from "@/components/chat/TicketApproval";
import { EvidencePanel } from "@/components/console/EvidencePanel";
import { SuggestedPrompts } from "@/components/console/SuggestedPrompts";

const WorkflowSteps = dynamic(
  () => import("@/components/chat/WorkflowSteps").then((m) => m.WorkflowSteps),
  { ssr: false },
);

function Console({ domain, authorization }: { domain: Domain; authorization?: string }) {
  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={authorization ? { Authorization: authorization } : undefined}
      showDevConsole={process.env.NODE_ENV !== "production"}
    >
      <div className="console">
        <div className="console-main">
          <div className="console-head">
            <span className="console-icon" aria-hidden>
              {domain.icon}
            </span>
            <div className="console-head-meta">
              <h2>{domain.label}</h2>
              <p className="muted">{domain.blurb}</p>
            </div>
            <span className={`pill ${domain.kind === "workflow" ? "neutral" : "ok"} console-kind`}>
              {domain.kind === "workflow" ? "workflow + HITL" : "grounded Q&A"}
            </span>
          </div>

          {domain.kind === "workflow" && (
            <>
              <WorkflowSteps />
              <TicketApproval />
            </>
          )}

          <SuggestedPrompts domain={domain} />

          <div className="console-chat copilotkit-chat-host">
            <CopilotChat agentId={domain.id} />
          </div>
        </div>

        <EvidencePanel domain={domain} />
      </div>
    </CopilotKitProvider>
  );
}

const center: React.CSSProperties = {
  display: "flex",
  height: "100%",
  minHeight: 360,
  alignItems: "center",
  justifyContent: "center",
  flexDirection: "column",
  gap: 16,
};

function AuthedConsole({ domain }: { domain: Domain }) {
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
    // Refresh before the ~1h expiry, else the live (OBO) chat silently 401s mid-session.
    const id = setInterval(acquire, 4 * 60 * 1000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [isAuthenticated, accounts, instance]);

  if (!isAuthenticated) {
    return (
      <div style={center}>
        <p>Entre para usar {branding.product}.</p>
        <button className="btn btn-solid" onClick={() => instance.loginRedirect({ scopes: apiScopes })}>
          Entrar com a Microsoft
        </button>
      </div>
    );
  }
  if (!token) return <div style={center}>Adquirindo token…</div>;
  return <Console domain={domain} authorization={`Bearer ${token}`} />;
}

export default function AssuranceConsole({ domainId }: { domainId: string }) {
  const domain = getDomain(domainId);
  if (!domain) {
    return (
      <div style={center}>
        <p className="muted">Domínio “{domainId}” não encontrado.</p>
      </div>
    );
  }
  if (!authConfigured) return <Console domain={domain} />;
  return <AuthedConsole domain={domain} />;
}
