"use client";

// Admin page — tenant onboarding, data-plane config + connection lifecycle. Visible only to
// the Admin role (the real gate is server-side on every /tenant endpoint). Client-only (MSAL).
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { AppShell } from "@/components/shell/AppShell";
import { useMyRoles, isAdmin } from "@/lib/auth/roles";

const Connections = dynamic(() => import("@/components/admin/Connections").then((m) => m.Connections), {
  ssr: false,
});

export default function AdminConnectionsPage() {
  const t = useTranslations("common");
  const ta = useTranslations("admin");
  const roles = useMyRoles();
  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">{t("loading")}</p>
      ) : isAdmin(roles) ? (
        <Connections />
      ) : (
        <div className="card">
          {ta.rich("needAdminConnections", { b: (c) => <b>{c}</b> })}
        </div>
      )}
    </AppShell>
  );
}
