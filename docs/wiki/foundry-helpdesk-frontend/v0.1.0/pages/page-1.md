# Fatos extraídos do código-fonte

## app/layout.tsx
- Exporta uma constante `metadata` com `title: branding.product` e `description: branding.description`. (app/layout.tsx)  
- Exporta por padrão a função `RootLayout` que renderiza:
  - um elemento `<html lang="en">`, com `<body style={{ margin: 0 }}>` contendo `<Providers>{children}</Providers>`. (app/layout.tsx)  
- Importa os estilos `@copilotkit/react-core/v2/styles.css` e `@/styles/globals.css`, e importa `Providers` e `branding`. (app/layout.tsx)

## app/page.tsx
- Define a constante `PILLARS`, um array de objetos com título (`title`), corpo (`body`) e etiqueta (`tag`). Os itens são:
  - Title: "Knowledge base", Body: "Foundry IQ agentic retrieval over the runbook corpus — answers cite their source or decline.", Tag: "Phase 1". (app/page.tsx)
  - Title: "Multi-agent workflow", Body: "triage → retrieve → resolve → escalate, streamed step-by-step to the UI over AG-UI.", Tag: "Phase 2". (app/page.tsx)
  - Title: "Memory + Entra OBO", Body: "Per-user memory, called on-behalf-of the signed-in developer via delegated tokens.", Tag: "Phase 3". (app/page.tsx)
  - Title: "Human-in-the-loop", Body: "Ticket escalation pauses for explicit approval before create_ticket ever fires.", Tag: "Phase 4". (app/page.tsx)
  - Title: "Evaluation", Body: "Deterministic policy gate + Foundry groundedness/relevance/coherence judges, linked to the portal.", Tag: "Phase 5". (app/page.tsx)
- Exporta por padrão o componente `Page` que renderiza:
  - Um `AppShell` que contém:
    - Uma seção com `<h1>Microsoft Foundry, end to end.</h1>`. (app/page.tsx)
    - Um parágrafo cujo texto é: "An internal engineering support concierge that triages, grounds answers in runbooks, remembers the developer, escalates with human approval — and is continuously evaluated. Every Foundry pillar, validated hands-on." (app/page.tsx)
    - Dois links:
      - Um `Link` para `/chat` com texto "💬 Open the concierge" e classes `btn btn-primary`. (app/page.tsx)
      - Um `Link` para `/evals` com texto "✓ View evaluations" e classes `btn btn-ghost`. (app/page.tsx)
    - Um título "Capabilities" e um grid que mapeia `PILLARS` para cartões onde cada cartão mostra o título, o corpo e uma `span` com a etiqueta seguida de "· green". (app/page.tsx)

## next.config.ts
- Define `nextConfig` com `output: "standalone"`. (next.config.ts)  
- Comentário no arquivo: "Emit a self-contained server bundle (.next/standalone) for the container image." (next.config.ts)

## package.json
- Nome do pacote: "foundry-helpdesk-frontend". Versão: "0.1.0". Campo `private: true`. (package.json)
- Scripts definidos: `dev`, `build`, `start`, `lint`, `typecheck`, `demo`, `demo:record` com os comandos mostrados no arquivo. (package.json)
- Dependências listadas (com as versões especificadas no arquivo), por exemplo: "@ag-ui/client": "^0.0.57", "@azure/msal-browser": "^5.15.0", "@copilotkit/react-core": "^1.61.2", "next": "^15.5.0", "react": "^19.0.0", entre outras. (package.json)
- DevDependencies listadas (com as versões especificadas), por exemplo: "@copilotkit/aimock": "^1.34.0", "@types/node": "^22.0.0", "typescript": "^5.6.0". (package.json)

## tsconfig.json
- Contém `compilerOptions` com várias configurações, incluindo `target: "ES2022"`, `lib: ["dom","dom.iterable","esnext"]`, `jsx: "preserve"`, `paths: { "@/*": ["./*"] }`, entre outras opções presentes no arquivo. (tsconfig.json)
- `include` contém ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"] e `exclude` contém ["node_modules"]. (tsconfig.json)

## next-env.d.ts
- Contém referências a tipos Next: `/// <reference types="next" />`, `/// <reference types="next/image-types/global" />` e `/// <reference path="./.next/types/routes.d.ts" />`. (next-env.d.ts)  
- Inclui o comentário: "NOTE: This file should not be edited". (next-env.d.ts)