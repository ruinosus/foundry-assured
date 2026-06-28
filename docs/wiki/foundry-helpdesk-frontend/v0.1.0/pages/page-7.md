# Informações extraídas do código-fonte

- O arquivo lib/demo.ts exporta a constante `demoMode` definida como `process.env.NEXT_PUBLIC_DEMO_MODE === "1"`. (lib/demo.ts)

- Comentário no arquivo lib/demo.ts:
  "Demo mode (no Azure). When NEXT_PUBLIC_DEMO_MODE=1, the app talks to an aimock AG-UI server replaying a recorded fixture instead of the real backend — so the whole flow (steps, grounded answer, HITL) runs with zero Azure and no sign-in. Set by scripts/demo.sh. See README › "Demo mode — see it with no Azure"." (lib/demo.ts)

- O arquivo app/page.tsx exporta um componente Page que renderiza, dentro de `AppShell`:
  - Um cabeçalho (h1) com o texto: "Microsoft Foundry, end to end." (app/page.tsx)
  - Um parágrafo com o texto: "An internal engineering support concierge that triages, grounds answers in runbooks, remembers the developer, escalates with human approval — and is continuously evaluated. Every Foundry pillar, validated hands-on." (app/page.tsx)
  - Dois links/buttons:
    - Link para "/chat" com o rótulo "💬 Open the concierge". (app/page.tsx)
    - Link para "/evals" com o rótulo "✓ View evaluations". (app/page.tsx)
  - Uma seção "Capabilities" que renderiza cards a partir da constante `PILLARS`. Cada card inclui título, corpo e uma tag seguida de "· green". (app/page.tsx)

- A constante `PILLARS` definida em app/page.tsx contém os seguintes itens:
  - Title: "Knowledge base"  
    Body: "Foundry IQ agentic retrieval over the runbook corpus — answers cite their source or decline."  
    Tag: "Phase 1" (app/page.tsx)
  - Title: "Multi-agent workflow"  
    Body: "triage → retrieve → resolve → escalate, streamed step-by-step to the UI over AG-UI."  
    Tag: "Phase 2" (app/page.tsx)
  - Title: "Memory + Entra OBO"  
    Body: "Per-user memory, called on-behalf-of the signed-in developer via delegated tokens."  
    Tag: "Phase 3" (app/page.tsx)
  - Title: "Human-in-the-loop"  
    Body: "Ticket escalation pauses for explicit approval before create_ticket ever fires."  
    Tag: "Phase 4" (app/page.tsx)
  - Title: "Evaluation"  
    Body: "Deterministic policy gate + Foundry groundedness/relevance/coherence judges, linked to the portal."  
    Tag: "Phase 5" (app/page.tsx)