"use client";

// Admin page — tenant onboarding, data-plane config + connection lifecycle. Visible only to
// the Admin role (the real gate is server-side on every /tenant endpoint). Client-only (MSAL).
import dynamic from "next/dynamic";
import { AppShell } from "@/components/shell/AppShell";
import { useMyRoles, isAdmin } from "@/lib/auth/roles";

const Connections = dynamic(() => import("@/components/admin/Connections").then((m) => m.Connections), {
  ssr: false,
});

export default function AdminConnectionsPage() {
  const roles = useMyRoles();
  return (
    <AppShell>
      {roles === null ? (
        <p className="muted">Loading…</p>
      ) : isAdmin(roles) ? (
        <Connections />
      ) : (
        <div className="card">
          You need the <b>Admin</b> role to manage connections. Ask an administrator to assign it,
          then sign out and back in so your token carries the role.
        </div>
      )}
    </AppShell>
  );
}
