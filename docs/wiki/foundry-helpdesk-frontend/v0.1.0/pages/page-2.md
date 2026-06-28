# Arquitetura e Stack Tecnológico

A seguir estão apenas fatos explicitamente presentes nos arquivos-fonte fornecidos, com citação do arquivo de origem.

## Container e build
- Imagem base de build: node:20-slim; etapa "build" instala dependências via `npm ci` e executa `npm run build`. (Dockerfile)  
- A etapa de execução usa node:20-slim em produção, expõe a porta 3000 e inicia com `node server.js`. (Dockerfile)  
- Variáveis de build públicas NEXT_PUBLIC_ENTRA_TENANT_ID, NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID e NEXT_PUBLIC_ENTRA_API_CLIENT_ID são declaradas como ARG e promovidas a ENV antes do build. (Dockerfile)

## Runtime CopilotKit / bridges para backend AG-UI
- Há uma rota runtime em `/api/copilotkit` que instancia um CopilotRuntime com agentes nomeados `helpdesk`, `helpdesk-hosted` e `cockpit`. (app/api/copilotkit/[[...slug]]/route.ts)  
- O agente `helpdesk` usa um HttpAgent cujo URL padrão é `http://localhost:8000/helpdesk` e que sobrepõe `fetch` para transformar um corpo JSON com `resume` em um formato com `interrupts` antes de encaminhar a requisição. (app/api/copilotkit/[[...slug]]/route.ts)  
- Há um agente `helpdesk-hosted` cujo URL padrão é `http://localhost:8000/helpdesk-hosted`. (app/api/copilotkit/[[...slug]]/route.ts)  
- Há um agente `cockpit` cujo URL padrão é `http://localhost:8000/cockpit`. (app/api/copilotkit/[[...slug]]/route.ts)

## Proxies de API para o backend (servidor Next)
- `/api/evals` faz proxy GET para `${BACKEND}/eval/foundry`, onde `BACKEND` padrão é `http://localhost:8000`; a rota encaminha o header Authorization da requisição de entrada quando presente e retorna JSON com runs ou erro. (app/api/evals/route.ts)  
- `/api/tickets` faz proxy GET para `${BACKEND}/tickets` e também encaminha o header Authorization quando presente; retorna JSON com tickets ou erro. (app/api/tickets/route.ts)  
- `/api/health` faz proxy GET para `${BACKEND}/healthz` e retorna JSON `{ ok: r.ok }` com status 200 quando `r.ok` é true, caso contrário status 502; em erro de fetch retorna `{ ok: false }` com status 502. (app/api/health/route.ts)  
- As rotas acima declaram `export const dynamic = "force-dynamic"`. (app/api/evals/route.ts, app/api/tickets/route.ts, app/api/health/route.ts)

## Estrutura da aplicação frontend (Next.js)
- O layout raiz importa estilos de `@copilotkit/react-core/v2/styles.css` e de `@/styles/globals.css`, usa um componente `Providers` e define metadata com `branding.product` e `branding.description`. (app/layout.tsx)  
- Páginas `/chat` e `/cockpit` carregam os componentes principais do chat com import dinâmico e `ssr: false`, e são componentes cliente (`"use client"`). (app/chat/page.tsx, app/cockpit/page.tsx)  
- A página principal (`/`) e as páginas `/evals` e `/tickets` usam `AppShell` para renderizar o conteúdo das rotas. (app/page.tsx, app/evals/page.tsx, app/tickets/page.tsx)

## CopilotKit no frontend
- O provedor CopilotKit é configurado para usar `runtimeUrl="/api/copilotkit"` e pode receber headers (por exemplo Authorization) passados ao provedor. (components/chat/HelpdeskApp.tsx, components/cockpit/CockpitApp.tsx)  
- `showDevConsole` para o CopilotKit é controlado por `process.env.NODE_ENV !== "production"`. (components/chat/HelpdeskApp.tsx, components/cockpit/CockpitApp.tsx)

## Autenticação (MSAL / Entra) e gerenciamento de tokens
- O código referencia `authConfigured`, `apiScopes` e inicialização MSAL; quando `authConfigured` é verdadeiro, há ramificações que usam MSAL hooks (`useMsal`, `useIsAuthenticated`) para autenticar e adquirir tokens. (components/chat/HelpdeskApp.tsx, components/cockpit/CockpitApp.tsx, components/shell/Providers.tsx, components/shell/AppShell.tsx)  
- Em fluxos autenticados, o token de acesso é obtido via `instance.acquireTokenSilent({ scopes: apiScopes, account })`, com fallback para `instance.acquireTokenRedirect({ scopes: apiScopes })`, e há um intervalo para renovar o token a cada 4 minutos (4 * 60 * 1000 ms). (components/chat/HelpdeskApp.tsx, components/cockpit/CockpitApp.tsx)  
- `Providers` inicializa `msalInstance` quando presente chamando `msalInstance.initialize()` e, quando `authConfigured` é verdadeiro, monta `MsalProvider` e um `AuthGate` que mostra `LoginScreen` enquanto não autenticado. (components/shell/Providers.tsx, components/shell/LoginScreen.tsx)

## Comportamentos de UI e componentes relevantes
- `AppShell` implementa uma barra lateral com navegação, usa `branding.product`, `branding.tagline` e um menu NAV que inclui links para "/", "/chat", "/cockpit", "/tickets", "/evals". (components/shell/AppShell.tsx)  
- `AppShell` consulta `/api/health` para determinar o status do backend e exibe um rótulo "backend online" / "backend offline" / "checking…" conforme o resultado. (components/shell/AppShell.tsx)  
- `LoginScreen` contém um botão que chama `instance.loginRedirect({ scopes: apiScopes })`. (components/shell/LoginScreen.tsx)

## Componentes de chat e fluxo ao vivo
- `HelpdeskApp` oferece dois modos (`live` e `hosted`) controlados por estado local; no modo `live` renderiza `WorkflowSteps`, `TicketApproval` e `CopilotChat agentId="helpdesk"`; no modo `hosted` renderiza `CopilotChat agentId="helpdesk-hosted"`. (components/chat/HelpdeskApp.tsx)  
- `CockpitApp` sempre renderiza `CopilotChat agentId="cockpit"`. (components/cockpit/CockpitApp.tsx)  
- `WorkflowSteps` subscreve o agente `helpdesk` para eventos (`onRunInitialized`, `onActivitySnapshotEvent`, `onRunFinalized`, `onRunFailed`) e apresenta três passos estáticos: `triage`, `retrieve`, `resolve`. (components/chat/WorkflowSteps.tsx)  
- `TicketApproval` subscreve o agente `helpdesk` e aguarda eventos CUSTOM com `name === "request_info"` para extrair `request_id` e `summary`; ao aprovar/rejeitar, chama `agent.runAgent({ resume: [{ interruptId, status: "resolved", payload: approved }] })`. (components/chat/TicketApproval.tsx)

## Visualização de avaliações (Evals)
- `EvalsView` faz fetch para `/api/evals` via `authedFetch("/api/evals")`, espera um objeto com `runs` e possivelmente `error`, e renderiza uma tabela de runs com campos como `id`, `eval_name`, `status`, `created_at`, `report_url`, `total`, `passed`, `failed`, `criteria`. (components/evals/EvalsView.tsx)  
- `EvalsView` define `FOUNDRY_PORTAL = "https://ai.azure.com"` e usa esse valor como fallback quando um run não tem `report_url`. (components/evals/EvalsView.tsx)  
- Quando não há runs, a view exibe instrução que inclui o comando literal `uv run python -m eval.run_eval --cloud` e referência literal a `apps/backend/` no texto exibido. (components/evals/EvalsView.tsx)

---

Todas as afirmações acima estão diretamente extraídas dos arquivos-fonte citados. Se desejar, posso gerar um documento mais organizado (diagramas, tabela de componentes, linhas de arquivo citadas) baseado exclusivamente nesses mesmos arquivos.