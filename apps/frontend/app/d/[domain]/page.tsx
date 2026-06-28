"use client";

// One route for every domain agent. The domain id comes from the path (/d/<id>) and is
// resolved against lib/domains.ts inside the console — adding a domain needs no new page.
// Client-only (MSAL + CopilotKit v2 can't run during SSR), rendered flush so the console
// fills the shell.

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";

const AssuranceConsole = dynamic(() => import("@/components/console/AssuranceConsole"), {
  ssr: false,
});

export default function DomainPage() {
  const params = useParams<{ domain: string }>();
  const domainId = Array.isArray(params.domain) ? params.domain[0] : params.domain;
  return (
    <AppShell flush>
      <AssuranceConsole domainId={domainId ?? ""} />
    </AppShell>
  );
}
