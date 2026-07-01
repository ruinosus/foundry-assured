// Single source of truth for the assistant domains.
//
// The whole point of the assurance mechanism is that it's domain-swappable — so the
// frontend is too. This registry drives the agent map (api/copilotkit route), the
// sidebar nav, the generic console route (/d/[domain]), the landing role-cards, and the
// per-domain starter prompts. Adding a domain = one entry here (+ a backend agent).

export type DomainKind = "workflow" | "grounded" | "tool";

export interface Domain {
  /** Stable id — matches the backend agentId + the AG-UI endpoint path segment. */
  id: string;
  icon: string;
  label: string;
  /** "workflow" = triage→retrieve→resolve→escalate with steps + HITL; "grounded" = pure cited
   * Q&A; "tool" = tool-driven (Microsoft MCP servers) with HITL on write actions. */
  kind: DomainKind;
  /** One line for the switcher + landing card. */
  blurb: string;
  /** Starter prompts shown as chips — avoids the "blank box, prompt paralysis" anti-pattern. */
  suggested: string[];
  /** Backend AG-UI path (default; per-domain env override resolved in the runtime route). */
  endpoint: string;
  /** Optional Foundry hosted twin agent id (enables the live-vs-hosted toggle). */
  hostedAgentId?: string;
}

export const DOMAINS: Domain[] = [
  {
    id: "helpdesk",
    icon: "💬",
    label: "Helpdesk concierge",
    kind: "workflow",
    blurb:
      "Triagem → fundamenta → resolve → escala, com aprovação humana antes de abrir um chamado.",
    suggested: [
      "Como faço rollback de um deploy em produção?",
      "Preciso de acesso de produção — abre um chamado pra mim?",
      "Meu pod está em CrashLoopBackOff, por onde começo?",
    ],
    endpoint: "/helpdesk",
  },
  {
    id: "cockpit",
    icon: "🛰️",
    label: "Cockpit expert",
    kind: "grounded",
    blurb:
      "Q&A fundamentado na base da plataforma Cockpit — cita o componente e o documento de cada afirmação.",
    suggested: [
      "Quais são todos os servidores MCP do Cockpit?",
      "Qual é a arquitetura do cockpit-portal-api?",
      "Como funciona a hierarquia de multi-tenancy?",
    ],
    endpoint: "/cockpit",
  },
  {
    id: "selfwiki",
    icon: "📖",
    label: "Project wiki",
    kind: "grounded",
    blurb:
      "Pergunte sobre este próprio repositório — a deep-wiki gerada do código real do monorepo.",
    suggested: [
      "Quais endpoints AG-UI o backend expõe?",
      "Como funciona o controle de acesso por documento?",
      "Quais são as fases de implementação do projeto?",
    ],
    endpoint: "/selfwiki",
  },
  {
    id: "platform",
    icon: "🛠️",
    label: "Platform ops",
    kind: "tool",
    blurb:
      "Concierge de plataforma sobre as ferramentas Microsoft (Learn, Azure, Entra, DevOps, GitHub) — com aprovação humana antes de qualquer ação de escrita.",
    suggested: [
      "O que é o Azure AI Foundry Agent Service? (via Microsoft Learn)",
      "Liste os recursos do meu resource group.",
      "Quanto gastei em AI Search neste mês?",
    ],
    endpoint: "/platform",
    hostedAgentId: "platform-hosted",
  },
];

export const getDomain = (id: string | undefined): Domain | undefined =>
  DOMAINS.find((d) => d.id === id);
