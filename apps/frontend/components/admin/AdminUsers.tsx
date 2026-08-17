"use client";

// Admin page: user lifecycle (invite / create / remove) + app-role assignment, all via the
// backend /admin/* (which holds the app-only Graph creds). Every call is re-gated server-side
// by the Admin role; this UI is the convenience layer.

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { authedFetch } from "@/lib/auth/api";

interface User {
  id: string;
  displayName?: string;
  userPrincipalName?: string;
  mail?: string;
  accountEnabled?: boolean;
}
interface Assignment {
  id: string;
  principalId?: string;
  principalDisplayName?: string;
  principalType?: string;
  role: string;
}

async function call(path: string, init?: RequestInit) {
  const r = await authedFetch(`/api/admin/${path}`, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.error || `error ${r.status}`);
  return data;
}

export function AdminUsers() {
  const t = useTranslations("admin");
  const [users, setUsers] = useState<User[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [u, a, r] = await Promise.all([
        call("users"),
        call("role-assignments"),
        call("roles"),
      ]);
      setUsers(u.users || []);
      setAssignments(a.assignments || []);
      setRoles(r.roles || []);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await fn();
      setMsg(ok);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // form state
  const [inviteEmail, setInviteEmail] = useState("");
  const [cName, setCName] = useState("");
  const [cUpn, setCUpn] = useState("");
  const [cPwd, setCPwd] = useState("");
  const [aPrincipal, setAPrincipal] = useState("");
  const [aRole, setARole] = useState("Reader");

  return (
    <div className="stack">
      <div>
        <h1>{t("usersTitle")}</h1>
        <p className="muted t-sm">
          Managed in Microsoft Entra via Graph — the app owns the roles
          ({roles.join(" · ") || "…"}); your company maps its groups onto them.
        </p>
      </div>

      {err && <div className="card btn btn-reject">⚠️ {err}</div>}
      {msg && <div className="card btn btn-approve">✓ {msg}</div>}

      {/* Role assignments */}
      <section className="card">
        <h3>{t("assignments")}</h3>
        <div className="table-wrap">
          <table className="evals">
            <thead><tr><th>{t("principal")}</th><th>Type</th><th>{t("role")}</th><th></th></tr></thead>
            <tbody>
              {assignments.length === 0 && <tr><td colSpan={4} className="muted">{t("noAssignments")}</td></tr>}
              {assignments.map((a) => (
                <tr key={a.id}>
                  <td>{a.principalDisplayName || a.principalId}</td>
                  <td><span className="pill neutral">{a.principalType || "—"}</span></td>
                  <td><span className="pill ok">{a.role}</span></td>
                  <td className="right">
                    <button className="acct-btn" disabled={busy}
                      onClick={() => run(() => call(`role-assignments/${a.id}`, { method: "DELETE" }), "Role revoked.")}>
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="row-tight">
          <input className="acct-btn grow" placeholder="Principal object-id (user or group)"
            value={aPrincipal} onChange={(e) => setAPrincipal(e.target.value)} />
          <select className="acct-btn" value={aRole} onChange={(e) => setARole(e.target.value)}>
            {roles.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <button className="btn btn-solid" disabled={busy || !aPrincipal}
            onClick={() => run(() => call("role-assignments", { method: "POST", body: JSON.stringify({ principal_id: aPrincipal, role: aRole }) }), "Role assigned.")}>
            Assign role
          </button>
        </div>
        <p className="muted t-xs">
          On this tenant, assign to a <b>user</b> object-id. Group assignment is the same call once the tenant has Entra ID P1.
        </p>
      </section>

      {/* Users */}
      <section className="card">
        <h3>{t("users")}</h3>
        <div className="table-wrap">
          <table className="evals">
            <thead><tr><th>Name</th><th>{t("upn")}</th><th>{t("enabled")}</th><th></th></tr></thead>
            <tbody>
              {users.length === 0 && <tr><td colSpan={4} className="muted">{t("noUsers")}</td></tr>}
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.displayName || "—"}</td>
                  <td className="muted">{u.userPrincipalName || u.mail || "—"}</td>
                  <td><span className={`pill ${u.accountEnabled ? "ok" : "bad"}`}>{u.accountEnabled ? "yes" : "no"}</span></td>
                  <td className="right">
                    <button className="acct-btn" disabled={busy}
                      onClick={() => { if (confirm(`Remove ${u.displayName || u.id}?`)) run(() => call(`users/${u.id}`, { method: "DELETE" }), "User removed."); }}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid g2 grid g2">
          <div>
            <h4>{t("invite")}</h4>
            <div className="row-tight">
              <input className="acct-btn grow" placeholder="email@company.com"
                value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
              <button className="btn btn-solid" disabled={busy || !inviteEmail}
                onClick={() => run(() => call("users/invite", { method: "POST", body: JSON.stringify({ email: inviteEmail }) }), "Invitation sent.")}>
                Invite
              </button>
            </div>
          </div>
          <div>
            <h4>{t("create")}</h4>
            <div className="stack-sm">
              <input className="acct-btn" placeholder="Display name" value={cName} onChange={(e) => setCName(e.target.value)} />
              <input className="acct-btn" placeholder="user@tenant.onmicrosoft.com" value={cUpn} onChange={(e) => setCUpn(e.target.value)} />
              <div className="row-tight">
                <input className="acct-btn grow" type="password" placeholder="Temp password" value={cPwd} onChange={(e) => setCPwd(e.target.value)} />
                <button className="btn btn-solid" disabled={busy || !cName || !cUpn || !cPwd}
                  onClick={() => run(() => call("users", { method: "POST", body: JSON.stringify({ display_name: cName, user_principal_name: cUpn, password: cPwd }) }), "User created.")}>
                  Create
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
