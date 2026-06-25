// CopilotKit runtime route — bridges the browser to the backend AG-UI endpoint,
// forwarding the user's Entra ID bearer token so the backend can do the OBO
// exchange and act as the signed-in user.
//
// Built per request so each call carries that request's Authorization header.

import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";

const AGUI_URL = process.env.AGUI_URL ?? "http://localhost:8000/helpdesk";

export const POST = async (req: NextRequest) => {
  const authorization = req.headers.get("authorization") ?? undefined;

  const runtime = new CopilotRuntime({
    agents: {
      helpdesk: new HttpAgent({
        url: AGUI_URL,
        headers: authorization ? { Authorization: authorization } : {},
      }),
    },
  });

  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
