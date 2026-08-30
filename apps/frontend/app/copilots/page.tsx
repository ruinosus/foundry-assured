import { AppShell } from "@/components/shell/AppShell";
import { CopilotCatalog } from "@/components/copilots/CopilotCatalog";

export default function Page() {
  return (
    <AppShell>
      <CopilotCatalog />
    </AppShell>
  );
}
