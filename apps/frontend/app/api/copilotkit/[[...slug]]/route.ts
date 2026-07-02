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

import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
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
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
// Per-domain env override: <ID>_AGUI_URL (e.g. COCKPIT_AGUI_URL, PLATFORM_AGUI_URL).
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
const runtime = new CopilotRuntime({
  // helpdesk + platform keep their hosted twins; grounded domains (cockpit, selfwiki) run live via OBO.
  // platform-hosted carries HITL (write-approval interrupt), so it uses the resume bridge.
  agents: {
    ...registryAgents,
    "helpdesk-hosted": helpdeskHosted,
    "platform-hosted": platformHosted,
  },
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
});

export const GET = handler;
export const POST = handler;
export const OPTIONS = handler;
