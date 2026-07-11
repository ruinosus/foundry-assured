"use client";

// Admin page: user lifecycle (invite / create / remove) + app-role assignment, all via the
// backend /admin/* (which holds the app-only Graph creds). Every call is re-gated server-side
// by the Admin role; this UI is the convenience layer.

import { useCallback, useEffect, useState } from "react";
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
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <h1 style={{ margin: "0 0 4px" }}>Users & roles</h1>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>
          Managed in Microsoft Entra via Graph — the app owns the roles
          ({roles.join(" · ") || "…"}); your company maps its groups onto them.
        </p>
      </div>

      {err && <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>⚠️ {err}</div>}
      {msg && <div className="card" style={{ borderColor: "var(--ok)", color: "var(--ok)" }}>✓ {msg}</div>}

      {/* Role assignments */}
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Role assignments</h3>
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table className="evals">
            <thead><tr><th>Principal</th><th>Type</th><th>Role</th><th></th></tr></thead>
            <tbody>
              {assignments.length === 0 && <tr><td colSpan={4} className="muted">No assignments yet.</td></tr>}
              {assignments.map((a) => (
                <tr key={a.id}>
                  <td>{a.principalDisplayName || a.principalId}</td>
                  <td><span className="pill neutral">{a.principalType || "—"}</span></td>
                  <td><span className="pill ok">{a.role}</span></td>
                  <td style={{ textAlign: "right" }}>
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
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
          <input className="acct-btn" style={{ flex: 1, minWidth: 220, cursor: "text" }} placeholder="Principal object-id (user or group)"
            value={aPrincipal} onChange={(e) => setAPrincipal(e.target.value)} />
          <select className="acct-btn" style={{ width: "auto" }} value={aRole} onChange={(e) => setARole(e.target.value)}>
            {roles.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <button className="btn btn-solid" disabled={busy || !aPrincipal}
            onClick={() => run(() => call("role-assignments", { method: "POST", body: JSON.stringify({ principal_id: aPrincipal, role: aRole }) }), "Role assigned.")}>
            Assign role
          </button>
        </div>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          On this tenant, assign to a <b>user</b> object-id. Group assignment is the same call once the tenant has Entra ID P1.
        </p>
      </section>

      {/* Users */}
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Users</h3>
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table className="evals">
            <thead><tr><th>Name</th><th>UPN / mail</th><th>Enabled</th><th></th></tr></thead>
            <tbody>
              {users.length === 0 && <tr><td colSpan={4} className="muted">No users loaded.</td></tr>}
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.displayName || "—"}</td>
                  <td className="muted">{u.userPrincipalName || u.mail || "—"}</td>
                  <td><span className={`pill ${u.accountEnabled ? "ok" : "bad"}`}>{u.accountEnabled ? "yes" : "no"}</span></td>
                  <td style={{ textAlign: "right" }}>
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

        <div className="grid g2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
          <div>
            <h4 style={{ margin: "0 0 8px" }}>Invite (external guest)</h4>
            <div style={{ display: "flex", gap: 8 }}>
              <input className="acct-btn" style={{ flex: 1, cursor: "text" }} placeholder="email@company.com"
                value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
              <button className="btn btn-solid" disabled={busy || !inviteEmail}
                onClick={() => run(() => call("users/invite", { method: "POST", body: JSON.stringify({ email: inviteEmail }) }), "Invitation sent.")}>
                Invite
              </button>
            </div>
          </div>
          <div>
            <h4 style={{ margin: "0 0 8px" }}>Create (internal member)</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <input className="acct-btn" style={{ cursor: "text" }} placeholder="Display name" value={cName} onChange={(e) => setCName(e.target.value)} />
              <input className="acct-btn" style={{ cursor: "text" }} placeholder="user@tenant.onmicrosoft.com" value={cUpn} onChange={(e) => setCUpn(e.target.value)} />
              <div style={{ display: "flex", gap: 8 }}>
                <input className="acct-btn" style={{ flex: 1, cursor: "text" }} type="password" placeholder="Temp password" value={cPwd} onChange={(e) => setCPwd(e.target.value)} />
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
