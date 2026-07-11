import { AppShell } from "@/components/shell/AppShell";
import { ArtifactDetail } from "@/components/artifacts/ArtifactDetail";

export default async function ArtifactDetailPage(
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return (
    <AppShell>
      <ArtifactDetail id={id} />
    </AppShell>
  );
}
