"use client";

// Assurance Console — the unified, config-driven surface for any domain agent.
//
// Two panes inside the (flush) shell: the chat (center) and the EvidencePanel (right,
// the citation/assurance signature). The AppShell sidebar is the domain switcher, so
// this is the same console for every domain — one route (/d/[domain]) drives all of them
// off lib/domains.ts. Workflow domains (helpdesk) additionally render the live steps +
// HITL approval; grounded domains are pure cited Q&A.
//
// Auth mirrors HelpdeskApp/TechDocsApp: when Entra is configured we gate on sign-in and
// forward the user's access token (the backend does the OBO exchange); otherwise the
// chat renders directly (dev/demo mode).

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { getDomain, type Domain } from "@/lib/domains";
import { GraphApproval } from "@/components/chat/GraphApproval";
import { TicketApproval } from "@/components/chat/TicketApproval";
import { EvidencePanel } from "@/components/console/EvidencePanel";
import { MermaidZoom } from "@/components/console/MermaidZoom";
import { SuggestedPrompts } from "@/components/console/SuggestedPrompts";

const WorkflowSteps = dynamic(
  () => import("@/components/chat/WorkflowSteps").then((m) => m.WorkflowSteps),
  { ssr: false },
);

// Which kinds stop for a human — and WHICH component asks. Three of the four interrupt;
// only `grounded` never does. This used to read `kind === "workflow"`, which was true when
// helpdesk was the only runtime and silently withheld the card from every runtime added
// after it: the interrupt arrived on the wire with nothing mounted to receive it.
//
// The two components are not interchangeable, and ADR-020 is why they are not merged:
// `graph` (LangGraph) goes through CopilotKit's own `useInterrupt`, while `workflow`/`tool`
// (Agent Framework) emit a `request_info` event that hook does not know about.
const AF_HITL_KINDS = new Set<Domain["kind"]>(["workflow", "tool"]);

function Console({ domain, authorization }: { domain: Domain; authorization?: string }) {
  const t = useTranslations("console");
  const locale = useLocale();
  // Live vs Hosted twin — registry-driven: only renders when the domain declares a
  // hostedAgentId, so any domain that later gains a Foundry hosted twin gets the toggle
  // for free (no per-domain special-casing here).
  const [mode, setMode] = useState<"live" | "hosted">("live");
  const activeAgentId =
    mode === "hosted" && domain.hostedAgentId ? domain.hostedAgentId : domain.id;

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
              <p className="console-blurb">{domain.blurb}</p>
            </div>
            {/* O que este domínio PROVA, não com que runtime foi feito. Antes lia
                KIND_LABEL[kind] — "grounded Q&A", "LangGraph + HITL" — vocabulário de
                implementação, que descreve o código para quem já o conhece e não diz nada a
                quem está avaliando se as garantias são reais. */}
            <p className="console-demo">
              <span className="console-demo-label">{t("demonstrates")}</span>
              {domain.demonstrates}
            </p>
          </div>

          {/* The steps panel reads the agent-framework workflow's state snapshots, so it
              stays workflow-only; the approval card is for every kind that interrupts. */}
          {domain.kind === "workflow" && <WorkflowSteps />}
          {AF_HITL_KINDS.has(domain.kind) && <TicketApproval agentId={activeAgentId} />}
          {domain.kind === "graph" && <GraphApproval agentId={activeAgentId} />}

          <SuggestedPrompts domain={domain} />

          {domain.hostedAgentId && (
            <div className="console-mode">
              <div className="seg">
                <button className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>
                  Live
                </button>
                <button
                  className={mode === "hosted" ? "on" : ""}
                  onClick={() => setMode("hosted")}
                >
                  Hosted
                </button>
              </div>
              <span className="console-mode-note">
                {mode === "live"
                  ? "AG-UI · live tool steps + write-approval"
                  : "Foundry Agent Service · managed hosted agent"}
              </span>
            </div>
          )}

          <div className="console-chat copilotkit-chat-host">
            <CopilotChat agentId={activeAgentId} />
            <MermaidZoom />
          </div>
        </div>

        <EvidencePanel domain={domain} />
      </div>
    </CopilotKitProvider>
  );
}

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
      <div className="console-center">
        <p>Entre para usar {branding.product}.</p>
        <button className="btn btn-primary" onClick={() => instance.loginRedirect({ scopes: apiScopes })}>
          Entrar com a Microsoft
        </button>
      </div>
    );
  }
  if (!token) return <div className="console-center">{useTranslations("common")("acquiringToken")}</div>;
  return <Console domain={domain} authorization={`Bearer ${token}`} />;
}

export default function AssuranceConsole({ domainId }: { domainId: string }) {
  const domain = getDomain(domainId);
  if (!domain) {
    return (
      <div className="console-center">
        <p className="muted">Domínio “{domainId}” não encontrado.</p>
      </div>
    );
  }
  if (!authConfigured) return <Console domain={domain} />;
  return <AuthedConsole domain={domain} />;
}
