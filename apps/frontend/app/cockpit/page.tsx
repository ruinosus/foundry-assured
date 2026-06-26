"use client";

// Client-only (MSAL + v2 useAgent can't run during SSR). Rendered flush so the
// Cockpit expert chat fills the shell.
import dynamic from "next/dynamic";
import { AppShell } from "@/components/shell/AppShell";

const CockpitApp = dynamic(() => import("@/components/cockpit/CockpitApp"), { ssr: false });

export default function CockpitPage() {
  return (
    <AppShell flush>
      <CockpitApp />
    </AppShell>
  );
}
