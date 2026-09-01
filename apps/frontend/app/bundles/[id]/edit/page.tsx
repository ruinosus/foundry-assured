import { AppShell } from "@/components/shell/AppShell";
import { BundleWorkspace } from "@/components/bundles/BundleWorkspace";

export default async function EditBundlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AppShell><BundleWorkspace bundleId={id} editing /></AppShell>;
}
