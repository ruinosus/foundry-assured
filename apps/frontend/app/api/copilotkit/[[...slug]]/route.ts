// CopilotKit runtime route — bridges the browser to the backend AG-UI endpoint.
//
// Catch-all (`[[...slug]]`) so the v2 client's sub-paths (e.g.
// `/api/copilotkit/agent/<id>/run`, runtime sync) reach the runtime handler — an
// exact `route.ts` only matches `/api/copilotkit` and 404s the agent-run calls.
//
// Resume format bridge: the CopilotKit runtime validates `resume` as an ARRAY
// (the AG-UI client form, [{ interruptId, status, payload }]), but the
// agent-framework backend expects a DICT ({ interrupts: [{ id, value }] }).
// We override the HttpAgent's fetch to translate the body just before it hits
// the backend, so the workflow interrupt can be resumed.

import {
  CopilotRuntime,
  InMemoryAgentRunner,
  createCopilotRuntimeHandler,
  type AgentRunnerConnectRequest,
} from "@copilotkit/runtime/v2";
import { Observable } from "rxjs";
import { fetchThreadHistory, historyConnectEvents } from "@/lib/thread-history";
import { HttpAgent } from "@ag-ui/client";
import { DOMAINS } from "@/lib/domains";

// Single base for the backend AG-UI endpoints. In the deployed web container BACKEND_URL is set
// (containerapps.bicep) to the backend FQDN; locally it falls back to localhost:8000. EVERY domain
// URL derives from this, so a new domain works in the cloud with no per-domain env var — the old
// per-domain *_AGUI_URL still override if set.
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const AGUI_URL = process.env.AGUI_URL ?? `${BACKEND}/helpdesk`;
// Phase 6: the hosted agent bridged to AG-UI (backend /helpdesk-hosted), so the
// "Hosted agent" toggle renders the same CopilotChat. No resume transform needed
// — the hosted path is request→response with no interrupts.
const HOSTED_AGUI_URL = process.env.HOSTED_AGUI_URL ?? `${BACKEND}/helpdesk-hosted`;
// D-runtime: the platform domain's hosted twin (backend /platform-hosted). Unlike
// helpdesk-hosted, the platform hosted path carries HITL (the write-approval interrupt
// over Invocations), so it goes through the resume bridge — not a bare HttpAgent.
const PLATFORM_HOSTED_AGUI_URL =
  process.env.PLATFORM_HOSTED_AGUI_URL ?? `${BACKEND}/platform-hosted`;

// Resume-format bridge (AG-UI `resume` array → agent-framework `{interrupts:[…]}` dict),
// needed by any domain with HITL interrupts (workflow + tool).
function withResumeBridge(url: string): HttpAgent {
  return new HttpAgent({
    url,
    fetch: async (u, requestInit) => {
      if (requestInit?.body && typeof requestInit.body === "string") {
        try {
          const body = JSON.parse(requestInit.body);
          if (Array.isArray(body.resume)) {
            body.resume = {
              interrupts: body.resume.map(
                (r: any) => ({ id: r.interruptId ?? r.id, value: r.payload ?? r.value }),
              ),
            };
            requestInit = { ...requestInit, body: JSON.stringify(body) };
          }
        } catch {
          // leave the body untouched if it isn't JSON
        }
      }
      return fetch(u, requestInit);
    },
  });
}

const helpdeskHosted = new HttpAgent({ url: HOSTED_AGUI_URL });
// Resume bridge (not a bare HttpAgent): platform-hosted has a write-approval interrupt.
const platformHosted = withResumeBridge(PLATFORM_HOSTED_AGUI_URL);

const urlFor = (d: { id: string; endpoint: string }) =>
  process.env[`${d.id.toUpperCase()}_AGUI_URL`] ?? `${BACKEND}${d.endpoint}`;

// Grounded domains are plain request→response. Interrupt-bearing domains (workflow + tool)
// get the resume bridge. Both come straight from the registry — adding a domain is one entry
// in lib/domains.ts (+ its backend agent), no per-domain wiring here.
// Per-domain env override: <ID>_AGUI_URL (e.g. TECHDOCS_AGUI_URL, PLATFORM_AGUI_URL).
const registryAgents = Object.fromEntries(
  DOMAINS.map((d) => [
    d.id,
    d.kind === "grounded"
      ? new HttpAgent({ url: urlFor(d) })
      : withResumeBridge(d.id === "helpdesk" ? AGUI_URL : urlFor(d)),
  ]),
);

// v2 multi-route runtime + fetch handler. The v2 client (react-core/react-ui 1.61.x) drives agent
// runs over sub-paths (POST /agent/:id/run, GET /info, …). createCopilotRuntimeHandler defaults to
// "multi-route", which serves exactly those. The legacy copilotRuntimeNextJSAppRouterEndpoint is
// SINGLE-route only (envelope { method } at /api/copilotkit) and 400s the agent-run sub-path with
// "Missing method field", which silently resets the chat. `basePath` strips the route prefix so the
// catch-all [[...slug]] segments match the multi-route patterns. (Diagnosed via the e2e harness.)


const staticAgents = {
  ...registryAgents,
  "helpdesk-hosted": helpdeskHosted,
  "platform-hosted": platformHosted,
};

/** O agente que a requisição está pedindo, extraído do caminho do runtime v2.
 *
 * O cliente v2 chama `/api/copilotkit/agent/<id>/run`. O id está ali, e é a única informação de
 * que precisamos para atender um agente que o registry não conhece.
 */
function requestedAgentId(url: string): string | null {
  const m = new URL(url).pathname.match(/\/agent\/([^/]+)\//);
  return m ? decodeURIComponent(m[1]) : null;
}

// Cache de processo dos agentes montados sob demanda. Sem ele, cada mensagem construiria um
// HttpAgent novo e o runtime perderia continuidade entre chamadas do mesmo agente.
const dynamicAgents: Record<string, HttpAgent> = {};

/** Um agente do FOUNDRY, montado na hora.
 *
 * ISTO FECHA O CICLO QUE ESTAVA ABERTO. O produto tinha um caminho para CRIAR agente (o wizard,
 * que publica no Foundry) e nenhum para USAR o que foi criado: o agent map nasce no import, a
 * partir do registry de código, então um agente criado depois não existia para o runtime. Quem
 * criasse pela tela o veria na lista e não teria o que fazer com ele.
 *
 * Registrar sob demanda evita o problema oposto — listar os agentes aqui exigiria autenticar no
 * backend a cada requisição do runtime, que roda sem o token do usuário. O id que o cliente pede
 * é suficiente: o backend valida o nome e recusa o que não existe.
 */
function agentFor(id: string): HttpAgent {
  dynamicAgents[id] ??= new HttpAgent({
    url: `${BACKEND}/foundry-agent/${encodeURIComponent(id)}`,
  });
  return dynamicAgents[id];
}

/** O runner que REIDRATA uma conversa no `connect`.
 *
 *  O runner padrão responde o `agent/connect` só da memória DO PROCESSO — ele nunca consulta o
 *  armazenamento durável. Depois de um restart, de uma réplica nova ou de uma sessão nova, o
 *  connect transmite nada e a conversa parece vazia até o próximo envio. Substitui o
 *  `ThreadSeeder`, que fazia isto pela tela: funcionava e amarrava a reidratação a um componente
 *  estar montado.
 *
 *  `onConcurrentRun: "supersede"` vem do dna-cloud, que pagou por ele em produção: o runner
 *  mantém um LOCK por thread, e um run que não finaliza — stream fechando sem RUN_FINISHED, o que
 *  um turno de HITL ou uma desconexão produzem — deixava o lock preso e todo envio seguinte
 *  falhava com "Thread already running". `supersede` aborta o run travado e começa o novo; a
 *  transcrição durável é a nossa, então esse sinalizador em memória nunca foi a fonte da verdade.
 */
class ThreadHistoryRunner extends InMemoryAgentRunner {
  constructor(private readonly headers: Record<string, string>) {
    super({ onConcurrentRun: "supersede" });
  }

  connect(request: AgentRunnerConnectRequest) {
    // Já há eventos em memória: esta é a thread corrente e o comportamento padrão está certo.
    if (this.getThreadEvents(request.threadId).length > 0) {
      return super.connect(request);
    }
    const cabecalhos = { ...this.headers, ...(request.headers ?? {}) };
    return new Observable((subscriber) => {
      let cancelado = false;
      void (async () => {
        const { messages } = await fetchThreadHistory(BACKEND, request.threadId, cabecalhos);
        if (cancelado) return;
        // `messages` é a forma CRUA vinda do backend — `historyConnectEvents` converte para
        // AG-UI e intercala os eventos de citação por dentro, usando o MESMO índice para os
        // dois (ver comentário de `idDaMensagem` em lib/thread-history.ts).
        const eventos = historyConnectEvents(request.threadId, messages);
        // O tipo do evento vem de um schema Zod do AG-UI, e o nosso construtor é puro (sem
        // importar o pacote de eventos, para continuar testável fora do runtime). O cast é o
        // preço dessa separação — e é onde ele fica, num lugar só, em vez de espalhado.
        for (const e of eventos) subscriber.next(e as any);
        subscriber.complete();
      })();
      return () => {
        cancelado = true;
      };
    }) as ReturnType<InMemoryAgentRunner["connect"]>;
  }
}

async function handler(req: Request): Promise<Response> {
  const id = requestedAgentId(req.url);
  // Um id conhecido do registry sempre ganha: os domínios do showcase têm runtime próprio
  // (workflow, grounded, graph) e não devem ser desviados para o caminho genérico.
  const agents =
    id && !(id in staticAgents) ? { ...staticAgents, [id]: agentFor(id) } : staticAgents;

  // O token do chamador viaja para o backend na reidratação: a conversa é escopada por usuário,
  // e sem ele o `by-id` responderia 401 — a tela abriria vazia sem dizer por quê.
  const auth = req.headers.get("authorization");

  return createCopilotRuntimeHandler({
    runtime: new CopilotRuntime({
      agents,
      runner: new ThreadHistoryRunner(auth ? { Authorization: auth } : {}),
    }),
    basePath: "/api/copilotkit",
  })(req);
}

export const GET = handler;
export const POST = handler;
export const OPTIONS = handler;
