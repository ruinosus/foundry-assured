"use client";

// Client-only (MSAL + CopilotKit v2 can't run during SSR — same reasoning as
// app/d/[domain]/page.tsx's AssuranceConsole).
import dynamic from "next/dynamic";
import { AppShell } from "@/components/shell/AppShell";

const ArtifactStudio = dynamic(
  () => import("@/components/artifacts/ArtifactStudio").then((m) => m.ArtifactStudio),
  { ssr: false },
);

export default function NewArtifactPage() {
  return (
    <AppShell>
      <ArtifactStudio />
    </AppShell>
  );
}
