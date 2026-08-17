import { AppShell } from "@/components/shell/AppShell";
import { FoundryAgentChat } from "@/components/agents/FoundryAgentChat";

export default async function AgentChatPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;
  return (
    <AppShell flush>
      <FoundryAgentChat name={decodeURIComponent(name)} />
    </AppShell>
  );
}
