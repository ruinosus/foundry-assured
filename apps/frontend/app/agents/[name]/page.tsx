import { AppShell } from "@/components/shell/AppShell";
import { AgentDetail } from "@/components/agents/AgentDetail";

export default async function AgentDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;
  return (
    <AppShell>
      <AgentDetail name={decodeURIComponent(name)} />
    </AppShell>
  );
}
