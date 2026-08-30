import { AppShell } from "@/components/shell/AppShell";
import { CopilotResource } from "@/components/copilots/CopilotResource";

export default async function Page({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  return (
    <AppShell>
      <CopilotResource nome={name} />
    </AppShell>
  );
}
