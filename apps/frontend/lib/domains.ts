// Single source of truth for the assistant domains.
//
// The whole point of the assurance mechanism is that it's domain-swappable — so the
// frontend is too. This registry drives the agent map (api/copilotkit route), the
// sidebar nav, the generic console route (/d/[domain]), the landing role-cards, and the
// per-domain starter prompts. Adding a domain = one entry here (+ a backend agent).
//
// O TEXTO NÃO MORA AQUI. Rótulo, descrição, o que o domínio prova e os prompts sugeridos vivem
// em `messages/<locale>.json` sob `domains.<id>`, lidos com `useTranslations("domains")`. O que
// fica é o que é CONTRATO com o backend (id, kind, endpoint) e não muda com o idioma.
//
// A divisão não é estética: este módulo é importado pela rota do CopilotKit, que roda no
// servidor sem contexto de idioma. Um campo de texto aqui é um campo que nasce numa língua só —
// foi assim que a tela de visão geral ficou em português fixo para quem escolheu inglês.
// `scripts/check-hardcoded-text.mjs` é o gate que impede a volta.

export type DomainKind = "workflow" | "grounded" | "tool" | "graph";

export interface Domain {
  /** Stable id — matches the backend agentId + the AG-UI endpoint path segment. */
  id: string;
  icon: string;
  /** "workflow" = triage→retrieve→resolve→escalate with steps + HITL; "grounded" = pure cited
   * Q&A; "tool" = tool-driven (Microsoft MCP servers) with HITL on write actions. */
  kind: DomainKind;
  /** Backend AG-UI path (default; per-domain env override resolved in the runtime route). */
  endpoint: string;
  /** Optional Foundry hosted twin agent id (enables the live-vs-hosted toggle). */
  hostedAgentId?: string;
}

export const DOMAINS: Domain[] = [
  {
    id: "helpdesk",
    icon: "💬",
    kind: "workflow",
    endpoint: "/helpdesk",
    // Foundry hosted twin (backend /helpdesk-hosted). The hosted agent runs inside Foundry, so the
    // backend invokes it via the agent endpoint (/agents/<name>/.../responses) — a path the MI IS
    // authorized for, unlike raw model inference (/openai/v1/responses) which 403s on this project.
    hostedAgentId: "helpdesk-hosted",
  },
  // TEMP: techdocs hidden from the app — its Foundry KB (techdocs-si-kb) isn't provisioned in this
  // env, so the domain 404s on retrieve. Corpus + backend agent are untouched; restore this block
  // (and ingest the KB) to bring it back.
  // {
  //   id: "techdocs",
  //   icon: "🛰️",
  //   label: "TechDocs expert",
  //   kind: "grounded",
  //   blurb:
  //     "Q&A fundamentado na base da plataforma TechDocs — cita o componente e o documento de cada afirmação.",
  //   suggested: [
  //     "Quais são todos os servidores MCP do TechDocs?",
  //     "Qual é a arquitetura do techdocs-portal-api?",
  //     "Como funciona a hierarquia de multi-tenancy?",
  //   ],
  //   endpoint: "/techdocs",
  //   // Grounded runs live via OBO — no hosted twin needed.
  // },
  {
    id: "selfwiki",
    icon: "📖",
    kind: "grounded",
    endpoint: "/selfwiki",
    // Grounded runs live via OBO — no hosted twin needed.
  },
  {
    id: "oncall",
    icon: "🚨",
    kind: "graph",
    endpoint: "/oncall",
    // No hosted twin: LangGraph runs in this backend, not inside Foundry.
  },
  {
    id: "platform",
    icon: "🛠️",
    kind: "tool",
    endpoint: "/platform",
    hostedAgentId: "platform-hosted",
  },
];

export const getDomain = (id: string | undefined): Domain | undefined =>
  DOMAINS.find((d) => d.id === id);
