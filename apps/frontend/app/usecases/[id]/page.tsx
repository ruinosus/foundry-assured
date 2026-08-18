import { AppShell } from "@/components/shell/AppShell";
import { UseCaseDetail } from "@/components/usecases/UseCaseDetail";

export default async function UseCasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell>
      <UseCaseDetail id={decodeURIComponent(id)} />
    </AppShell>
  );
}
