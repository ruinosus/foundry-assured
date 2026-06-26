// CopilotKit runtime route — bridges the browser to the backend AG-UI endpoint.
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

// Second domain: the Cockpit expert (grounded over the cockpit-kb). Plain HttpAgent
// — request→response grounded Q&A, no interrupts/resume transform needed.
const COCKPIT_AGUI_URL = process.env.COCKPIT_AGUI_URL ?? "http://localhost:8000/cockpit";
const cockpit = new HttpAgent({ url: COCKPIT_AGUI_URL });

const runtime = new CopilotRuntime({
  agents: { helpdesk, "helpdesk-hosted": helpdeskHosted, cockpit },
});

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
