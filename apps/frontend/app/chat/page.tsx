"use client";

// Client-only: the concierge uses MSAL + the v2 useAgent subscription, neither
// of which can run during SSR. Rendered flush so the chat fills the shell.
import dynamic from "next/dynamic";
import { AppShell } from "@/components/shell/AppShell";

const HelpdeskApp = dynamic(() => import("@/components/chat/HelpdeskApp"), { ssr: false });

export default function ChatPage() {
  return (
    <AppShell flush>
      <HelpdeskApp />
    </AppShell>
  );
}
