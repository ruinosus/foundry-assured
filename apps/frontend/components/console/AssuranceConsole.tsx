"use client";

// Assurance Console — the unified, config-driven surface for any domain agent.
//
// Two panes inside the (flush) shell: the chat (center) and a side column (right) with the
// conversation list and the static assurance guarantees (EvidencePanel). The citation evidence
// itself lives UNDER each response now (MessageEvidence.tsx) — the side column no longer carries
// it. The AppShell sidebar is the domain switcher, so this is the same console for every domain —
// one route (/d/[domain]) drives all of them off lib/domains.ts. Workflow domains (helpdesk)
// additionally render the live steps + HITL approval; grounded domains are pure cited Q&A.
//
// Auth mirrors HelpdeskApp/TechDocsApp: when Entra is configured we gate on sign-in and
// forward the user's access token (the backend does the OBO exchange); otherwise the
// chat renders directly (dev/demo mode).

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { CitationsProvider } from "@/lib/citations";
import { getDomain, type Domain } from "@/lib/domains";
import { GraphApproval } from "@/components/chat/GraphApproval";
import { TicketApproval } from "@/components/chat/TicketApproval";
import { ConversationsPanel } from "@/components/console/ConversationsPanel";
import { DomainPicker } from "@/components/console/DomainPicker";
import { EvidencePanel } from "@/components/console/EvidencePanel";
import { makeAssistantMessage } from "@/components/console/MessageEvidence";
import { MermaidZoom } from "@/components/console/MermaidZoom";
import { ShareButton } from "@/components/console/ShareButton";
import { SourceViewer } from "@/components/console/SourceViewer";
import { SuggestedPrompts } from "@/components/console/SuggestedPrompts";
import { ToolActivity } from "@/components/console/ToolActivity";
import { PARAMETRO_CONVERSA } from "@/lib/conversation-url";

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
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<"conv" | "ev">("conv");
  const [mode, setMode] = useState<"live" | "hosted">("live");
  const activeAgentId =
    mode === "hosted" && domain.hostedAgentId ? domain.hostedAgentId : domain.id;

  // A conversa ativa vive na URL (`?c=<threadId>`) — abrir o link começa NAQUELA conversa em vez
  // de criar uma nova, e é o que permite compartilhar (ShareButton) e sobreviver a um F5 (antes,
  // um reload sorteava um `crypto.randomUUID()` novo e a conversa "sumia", mesmo gravada no
  // backend). Lido só na MONTAGEM: dali em diante o estado do React manda, e a URL é espelho — o
  // efeito abaixo escreve nela, nunca o contrário (ver o comentário lá para o porquê).
  const [threadId, setThreadId] = useState<string>(
    () => searchParams.get(PARAMETRO_CONVERSA) || crypto.randomUUID(),
  );

  // Espelha a conversa ativa na URL SEM navegar — `history.replaceState`, não o router do Next.
  //
  // POR QUE `history.replaceState` e não `router.replace()`. Isto não é uma navegação: é
  // sincronizar a barra de endereço com um estado que já mudou na tela (nova conversa, ou
  // conversa aberta pelo painel). `router.replace()` do App Router entra no ciclo de transição do
  // Next — reavalia a árvore da rota a cada chamada — e faria isso a cada nova conversa/troca
  // sem motivo, correndo o risco de um re-render que reseta o `CopilotChat` que a troca de
  // `threadId` já cuida de remontar sozinha. `history.replaceState` só troca a URL visível, sem
  // tocar em React nem em rede.
  //
  // `replaceState`, não `pushState`: cada nova conversa ou troca de conversa não deve virar um
  // degrau no botão Voltar — voltar entre quarenta conversas trocadas ao longo de uma sessão não
  // é "página anterior" para quem está usando o produto, e empurrar mesmo assim quebraria a
  // navegação do navegador (Voltar nunca sairia da tela do console).
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set(PARAMETRO_CONVERSA, threadId);
    window.history.replaceState(null, "", url);
  }, [threadId]);

  // A gravação é por DOMÍNIO, não pelo gêmeo hospedado: live e hosted são a mesma conversa do
  // ponto de vista de quem conversa, e separá-las esconderia metade do histórico ao alternar.
  const conversationKey = domain.id;

  // `messageView` novo a cada render remontaria TODO o histórico: o `MemoizedAssistantMessage`
  // do CopilotKit compara IDENTIDADE do componente (não o que ele renderiza), então trocar de
  // aba, alternar Live/Hosted ou abrir outra conversa desmontava e remontava o balão inteiro
  // (Mermaid re-renderizando, rolagem saltando). `makeAssistantMessage` só precisa mudar quando
  // o domínio muda — é ele quem fecha o `domainId` usado no clique da citação.
  const messageView = useMemo(
    () => ({ assistantMessage: makeAssistantMessage(domain.id) }),
    [domain.id],
  );

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
              <ShareButton agent={domain.id} conversationId={threadId} />
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
            {/* A evidência é da MENSAGEM, não da sessão: o provider assina o mesmo agente do
                chat e arquiva as citações por message_id (ver lib/citations.tsx). A Task 5/6
                consomem `useCitationsFor` dentro deste subtree. */}
            <CitationsProvider agentId={activeAgentId}>
              {/* Vale para TODOS os domínios, não só os tool-driven: qualquer tool sem
                  renderizador próprio passa a aparecer em vez de virar spinner. */}
              <ToolActivity />
              <CopilotChat agentId={activeAgentId} threadId={threadId} messageView={messageView} />
              <MermaidZoom />
              <SourceViewer />
            </CitationsProvider>
          </div>
        </div>

        {/* UM painel, duas abas. A evidência de cada resposta já mora sob a própria resposta
            (ver MessageEvidence.tsx) — esta coluna lateral guarda só a lista de conversas e as
            garantias estáticas de assurance, então não há mais citação para contar aqui. A aba
            não troca sozinha ao trocar de mensagem: troca de contexto automática tiraria o
            usuário de onde ele estava. */}
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
              {t("tabGuarantees")}
            </button>
          </div>

          {/* Os dois ficam MONTADOS e um é escondido por CSS: o ConversationsPanel preserva
              posição de rolagem e estado ao trocar de aba em vez de recarregar a lista toda
              vez. O EvidencePanel agora é estático (só as garantias) e não tem estado a
              perder, mas escondê-lo por CSS em vez de desmontar continua sendo o caminho mais
              simples aqui — não há motivo para os dois painéis usarem estratégias diferentes. */}
          <div className={tab === "conv" ? "" : "tab-off"}>
            <ConversationsPanel
              agent={conversationKey}
              activeId={threadId}
              onOpen={setThreadId}
              onNew={() => setThreadId(crypto.randomUUID())}
            />
          </div>
          <div className={tab === "ev" ? "" : "tab-off"}>
            <EvidencePanel />
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
