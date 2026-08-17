"use client";

// Admin page — user lifecycle + role assignment. Visible only to the Admin role (the real
// gate is server-side on every /admin endpoint). Client-only (MSAL + per-user fetch).
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { AppShell } from "@/components/shell/AppShell";
import { useMyRoles, isAdmin } from "@/lib/auth/roles";

const AdminUsers = dynamic(() => import("@/components/admin/AdminUsers").then((m) => m.AdminUsers), {
  ssr: false,
});

export default function AdminUsersPage() {
  const t = useTranslations("common");
  const ta = useTranslations("admin");
  const roles = useMyRoles();
  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">{t("loading")}</p>
      ) : isAdmin(roles) ? (
        <AdminUsers />
      ) : (
        <div className="card">
          {ta.rich("needAdminUsers", { b: (c) => <b>{c}</b> })}
        </div>
      )}
    </AppShell>
  );
}
