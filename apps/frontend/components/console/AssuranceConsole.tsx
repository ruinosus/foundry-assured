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
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { getDomain, type Domain } from "@/lib/domains";
import { GraphApproval } from "@/components/chat/GraphApproval";
import { TicketApproval } from "@/components/chat/TicketApproval";
import { ConversationsPanel } from "@/components/console/ConversationsPanel";
import { DomainPicker } from "@/components/console/DomainPicker";
import { EvidencePanel } from "@/components/console/EvidencePanel";
import { MermaidZoom } from "@/components/console/MermaidZoom";
import { SuggestedPrompts } from "@/components/console/SuggestedPrompts";
import { ToolActivity } from "@/components/console/ToolActivity";

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
  const td = useTranslations("domains");
  const locale = useLocale();
  // Live vs Hosted twin — registry-driven: only renders when the domain declares a
  // hostedAgentId, so any domain that later gains a Foundry hosted twin gets the toggle
  // for free (no per-domain special-casing here).
  const router = useRouter();
  const [tab, setTab] = useState<"conv" | "ev">("conv");
  const [mode, setMode] = useState<"live" | "hosted">("live");
  const activeAgentId =
    mode === "hosted" && domain.hostedAgentId ? domain.hostedAgentId : domain.id;

  // A conversa ativa. Começa vazia e o CopilotKit cria a sua; ao abrir uma anterior, o id passa a
  // ser prop-controlado e o backend continua NAQUELA conversa (o HistoryProvider carrega o
  // histórico pelo mesmo id).
  const [threadId, setThreadId] = useState<string>(() => crypto.randomUUID());
  // A gravação é por DOMÍNIO, não pelo gêmeo hospedado: live e hosted são a mesma conversa do
  // ponto de vista de quem conversa, e separá-las esconderia metade do histórico ao alternar.
  const conversationKey = domain.id;

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
          {/* BARRA DE TOPO. Antes eram quatro blocos antes de qualquer conversa: ícone,
              título, subtítulo e "Demonstra" + parágrafo. O nome agora está no seletor; o
              `kind` fica discreto à direita; e o texto de vitrine desceu para a página de
              Casos de uso, que existe exatamente para isso. */}
          <div className="console-bar">
            <DomainPicker current={domain} onPick={(id) => router.push(`/d/${id}`)} />
            <div className="console-bar-end">
              <span className="t-xs t-mono muted-line">{domain.kind}</span>
              {domain.hostedAgentId && (
                <div className="seg seg-sm">
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
              )}
            </div>
          </div>

          {/* The steps panel reads the agent-framework workflow's state snapshots, so it
              stays workflow-only; the approval card is for every kind that interrupts. */}
          {domain.kind === "workflow" && <WorkflowSteps />}
          {AF_HITL_KINDS.has(domain.kind) && <TicketApproval agentId={activeAgentId} />}
          {domain.kind === "graph" && <GraphApproval agentId={activeAgentId} />}

          <SuggestedPrompts domain={domain} />


          <div className="console-chat copilotkit-chat-host">
            {/* Vale para TODOS os domínios, não só os tool-driven: qualquer tool sem
                renderizador próprio passa a aparecer em vez de virar spinner. */}
            <ToolActivity />
            <CopilotChat agentId={activeAgentId} threadId={threadId} />
            <MermaidZoom />
          </div>
        </div>

        {/* UM painel, duas abas. Antes eram três blocos empilhados disputando a mesma coluna,
            e dois deles só têm conteúdo DEPOIS de uma resposta com citação — ocupavam metade da
            altura exibindo o texto que explica o que apareceria ali.

            A aba não troca sozinha quando chega citação: troca de contexto automática tira o
            usuário de onde ele estava. O contador na aba avisa que há fonte nova. */}
        <div className="console-side">
          <div className="seg-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={tab === "conv"}
              className={tab === "conv" ? "on" : ""}
              onClick={() => setTab("conv")}
            >
              {t("tabConversations")}
            </button>
            <button
              role="tab"
              aria-selected={tab === "ev"}
              className={tab === "ev" ? "on" : ""}
              onClick={() => setTab("ev")}
            >
              {t("tabEvidence")}
            </button>
          </div>

          {/* Os dois ficam MONTADOS e um é escondido por CSS: o EvidencePanel assina o stream do
              agente, e desmontá-lo perderia as citações que chegam enquanto a aba de conversas
              está aberta — o contador nunca acenderia. */}
          <div className={tab === "conv" ? "" : "tab-off"}>
            <ConversationsPanel
              agent={conversationKey}
              activeId={threadId}
              onOpen={setThreadId}
              onNew={() => setThreadId(crypto.randomUUID())}
            />
          </div>
          <div className={tab === "ev" ? "" : "tab-off"}>
            <EvidencePanel domain={domain} />
          </div>
        </div>
      </div>
    </CopilotKitProvider>
  );
}

function AuthedConsole({ domain }: { domain: Domain }) {
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
        <p>{tc("signInToUse", { product: branding.product })}</p>
        <button className="btn btn-primary" onClick={() => instance.loginRedirect({ scopes: apiScopes })}>
          {tc("signIn")}
        </button>
      </div>
    );
  }
  if (!token) return <div className="console-center">{tc("acquiringToken")}</div>;
  return <Console domain={domain} authorization={`Bearer ${token}`} />;
}

export default function AssuranceConsole({ domainId }: { domainId: string }) {
  const tc = useTranslations("common");
  const domain = getDomain(domainId);
  if (!domain) {
    return (
      <div className="console-center">
        <p className="muted">{tc("domainNotFound", { id: domainId })}</p>
      </div>
    );
  }
  if (!authConfigured) return <Console domain={domain} />;
  return <AuthedConsole domain={domain} />;
}
