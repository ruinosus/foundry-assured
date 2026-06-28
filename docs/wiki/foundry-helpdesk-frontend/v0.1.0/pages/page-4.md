# Componentes e Fluxos de UI

- Rotas principais:
  - /chat: página client-only que renderiza o AppShell com flush e carrega dinamicamente o HelpdeskApp (app/chat/page.tsx).
  - /cockpit: página client-only que renderiza o AppShell com flush e carrega dinamicamente o CockpitApp (app/cockpit/page.tsx).
  - /evals: página que renderiza AppShell com EvalsView (app/evals/page.tsx).
  - /tickets: página que renderiza AppShell com TicketsView (app/tickets/page.tsx).

- App shell e navegação:
  - O AppShell fornece uma barra lateral fixa com navegação, um topo com breadcrumbs e envolve o conteúdo da rota (components/shell/AppShell.tsx).
  - O AppShell mostra a marca e rótulos derivados de branding (components/shell/AppShell.tsx).
  - O estado ativo da navegação e o título do breadcrumb são derivados do pathname atual (components/shell/AppShell.tsx).
  - O AppShell inclui um indicador de status do backend que verifica /api/health (components/shell/AppShell.tsx).
  - Quando authConfigured é true, o AppShell renderiza um componente de conta que usa MSAL para login/logout e mostra informações da conta (components/shell/AppShell.tsx).

- Provedores e controle de autenticação:
  - Providers inicializa MSAL (quando disponível) antes de montar o app e, se authConfigured for false, passa os children diretamente (components/shell/Providers.tsx).
  - Quando Entra está configurado (authConfigured), Providers monta MsalProvider e usa um AuthGate que mostra a tela de login enquanto o usuário não estiver autenticado (components/shell/Providers.tsx).
  - LoginScreen é uma tela de login em página cheia que dispara instance.loginRedirect com apiScopes (components/shell/LoginScreen.tsx).

- Helpdesk (concierge) — HelpdeskApp:
  - HelpdeskApp é carregado dinamicamente no cliente e, quando authConfigured é false, renderiza o chat diretamente; caso contrário, exige autenticação e adquire token via MSAL antes de passar Authorization ao runtime (components/chat/HelpdeskApp.tsx).
  - O chat usa CopilotKitProvider com runtimeUrl "/api/copilotkit" e passa headers Authorization quando disponível; showDevConsole é controlado por NODE_ENV (components/chat/HelpdeskApp.tsx).
  - O componente apresenta um modo selecionável "live" ou "hosted" (estado local), onde:
    - modo "live": renderiza WorkflowSteps, TicketApproval e CopilotChat com agentId "helpdesk" (components/chat/HelpdeskApp.tsx).
    - modo "hosted": renderiza CopilotChat com agentId "helpdesk-hosted" (components/chat/HelpdeskApp.tsx).
  - Em demoMode o toggle é ocultado e uma indicação de demo é mostrada (components/chat/HelpdeskApp.tsx).
  - Quando autenticado via MSAL, o componente adquire tokens silenciosamente com apiScopes e os renova periodicamente; enquanto não houver token exibe estados de "Sign in" ou "Acquiring token…" conforme apropriado (components/chat/HelpdeskApp.tsx).

- Cockpit expert — CockpitApp:
  - CockpitApp é carregado dinamicamente no cliente e usa CopilotKitProvider com runtimeUrl "/api/copilotkit"; também condiciona a passagem de Authorization quando disponível e controla showDevConsole por NODE_ENV (components/cockpit/CockpitApp.tsx).
  - O layout inclui uma nota explicativa e um CopilotChat com agentId "cockpit" (components/cockpit/CockpitApp.tsx).
  - Quando authConfigured é true, CockpitApp exige autenticação e adquire tokens via MSAL, renovando-os periodicamente; enquanto o token é obtido mostra "Acquiring token…" (components/cockpit/CockpitApp.tsx).

- Workflow steps:
  - WorkflowSteps exibe passos fixos (triage, retrieve, resolve) e mantém estado por executor, assinando o stream de eventos do agent (useAgent) para onRunInitialized, onActivitySnapshotEvent, onRunFinalized e onRunFailed (components/chat/WorkflowSteps.tsx).
  - Ao finalizar a execução, todos os passos são marcados como "completed" (components/chat/WorkflowSteps.tsx).

- Aprovação humano‑na‑loop (TicketApproval):
  - TicketApproval subscreve eventos do agent (useAgent) e escuta eventos CUSTOM com name "request_info"; extrai request_id (ou id) e resumo, exibindo um cartão de aprovação quando presente (components/chat/TicketApproval.tsx).
  - Ao aprovar/rejeitar, TicketApproval chama agent.runAgent com resume contendo interruptId, status "resolved" e payload booleano (components/chat/TicketApproval.tsx).

- Avaliações (EvalsView):
  - EvalsView busca /api/evals via authedFetch, mostra listas de runs com critérios e links para report_url quando presente; fornece link para o portal padrão FOUNDRY_PORTAL e botão de refresh que recarrega a lista (components/evals/EvalsView.tsx).
  - Mensagens de erro e estados de loading/empty são tratadas conforme a resposta do backend (components/evals/EvalsView.tsx).

- Tickets (TicketsView):
  - TicketsView busca /api/tickets via authedFetch e exibe uma tabela de tickets com id, summary, severity, status e created_at formatado; também fornece botão de refresh (components/tickets/TicketsView.tsx).
  - O texto descreve que os tickets são abertos pelo create_ticket tool após aprovação na conversa (comentário/descrição no componente) (components/tickets/TicketsView.tsx).