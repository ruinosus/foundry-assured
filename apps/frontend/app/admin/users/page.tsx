"use client";

// Admin page — user lifecycle + role assignment. Visible only to the Admin role (the real
// gate is server-side on every /admin endpoint). Client-only (MSAL + per-user fetch).
import dynamic from "next/dynamic";
import { AppShell } from "@/components/shell/AppShell";
import { useMyRoles, isAdmin } from "@/lib/auth/roles";

const AdminUsers = dynamic(() => import("@/components/admin/AdminUsers").then((m) => m.AdminUsers), {
  ssr: false,
});

export default function AdminUsersPage() {
  const roles = useMyRoles();
  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">Loading…</p>
      ) : isAdmin(roles) ? (
        <AdminUsers />
      ) : (
        <div className="card">
          You need the <b>Admin</b> role to manage users. Ask an administrator to assign it,
          then sign out and back in so your token carries the role.
        </div>
      )}
    </AppShell>
  );
}
