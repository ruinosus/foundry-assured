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
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";
import { DOMAINS } from "@/lib/domains";

const AGUI_URL = process.env.AGUI_URL ?? "http://localhost:8000/helpdesk";
// Phase 6: the hosted agent bridged to AG-UI (backend /helpdesk-hosted), so the
// "Hosted agent" toggle renders the same CopilotChat. No resume transform needed
// — the hosted path is request→response with no interrupts.
const HOSTED_AGUI_URL =
  process.env.HOSTED_AGUI_URL ?? "http://localhost:8000/helpdesk-hosted";

const helpdesk = new HttpAgent({
  url: AGUI_URL,
  fetch: async (url, requestInit) => {
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
    return fetch(url, requestInit);
  },
});

const helpdeskHosted = new HttpAgent({ url: HOSTED_AGUI_URL });

// Grounded domains (Cockpit, selfwiki, …) are plain request→response Q&A — no resume
// bridge needed — so they're built straight from the domains registry. Adding a domain
// is one entry in lib/domains.ts (+ its backend agent); no per-domain wiring here.
// Per-domain env override: <ID>_AGUI_URL (e.g. COCKPIT_AGUI_URL, SELFWIKI_AGUI_URL).
const groundedAgents = Object.fromEntries(
  DOMAINS.filter((d) => d.kind === "grounded").map((d) => {
    const override = process.env[`${d.id.toUpperCase()}_AGUI_URL`];
    return [d.id, new HttpAgent({ url: override ?? `http://localhost:8000${d.endpoint}` })];
  }),
);

const runtime = new CopilotRuntime({
  // helpdesk keeps its bespoke wiring (workflow resume bridge + hosted twin); the rest
  // come from the registry.
  agents: { helpdesk, "helpdesk-hosted": helpdeskHosted, ...groundedAgents },
});

const handle = (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};

export const GET = handle;
export const POST = handle;
