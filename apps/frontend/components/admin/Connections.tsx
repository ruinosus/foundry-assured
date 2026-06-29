"use client";

// Admin page: tenant onboarding + data-plane config + connection lifecycle, all via the
// backend /tenant/* (which holds the app-only creds). Every call is re-gated server-side by
// the Admin role; this UI is the convenience layer. No secrets are ever entered here — the
// connection references a Foundry connection or a Key Vault secret by id/ref, never the value.

import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

const KINDS = ["github", "azdo", "azure", "entra", "learn", "m365"] as const;
const ROLES = ["Reader", "Author", "Approver", "Admin"] as const;

interface DataPlane {
  foundry_project_endpoint?: string;
  foundry_model?: string;
  azure_search_endpoint?: string;
  azure_search_knowledge_base?: string;
  [k: string]: unknown;
}
interface Connection {
  id: string;
  kind: string;
  label: string;
  foundry_connection_id?: string;
  keyvault_ref?: string;
  min_role_read?: string;
  min_role_write?: string;
  enabled?: boolean;
}
interface TenantRecord {
  tid: string;
  name: string;
  tier?: string;
  status?: string;
  data_plane: DataPlane;
  connections: Connection[];
}
interface TenantResponse {
  onboarded: boolean;
  can_onboard?: boolean;
  record?: TenantRecord;
}

async function call(path: string, init?: RequestInit) {
  const r = await authedFetch(`/api/tenant/${path}`, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.error || `error ${r.status}`);
  return data;
}

const emptyForm = {
  id: "",
  kind: KINDS[0] as string,
  label: "",
  foundry_connection_id: "",
  keyvault_ref: "",
  min_role_read: "Reader" as string,
  min_role_write: "Approver" as string,
  enabled: true,
};

export function Connections() {
  const [tenant, setTenant] = useState<TenantResponse | null>(null);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // data-plane form state
  const [dp, setDp] = useState<DataPlane>({});
  // connection form state
  const [form, setForm] = useState({ ...emptyForm });

  const load = useCallback(async () => {
    setErr(null);
    try {
      const t: TenantResponse = await call("");
      setTenant(t);
      if (t.onboarded && t.record) {
        setDp({ ...t.record.data_plane });
        const c = await call("connections");
        setConnections(Array.isArray(c) ? c : c.connections || []);
      }
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

  const onboarded = !!tenant?.onboarded;
  const record = tenant?.record;

  const editConn = (c: Connection) => {
    setForm({
      id: c.id,
      kind: c.kind,
      label: c.label,
      foundry_connection_id: c.foundry_connection_id || "",
      keyvault_ref: c.keyvault_ref || "",
      min_role_read: c.min_role_read || "Reader",
      min_role_write: c.min_role_write || "Approver",
      enabled: c.enabled ?? true,
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <h1 style={{ margin: "0 0 4px" }}>Connections</h1>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>
          Onboard this tenant, point it at your Foundry data plane, and wire up the source
          connections. Secrets live in Foundry / Key Vault — only references are stored here.
        </p>
      </div>

      {err && <div className="card" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>⚠️ {err}</div>}
      {msg && <div className="card" style={{ borderColor: "var(--ok)", color: "var(--ok)" }}>✓ {msg}</div>}

      {/* Onboarding banner */}
      {tenant && !onboarded && (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Tenant not onboarded</h3>
          {tenant.can_onboard ? (
            <>
              <p className="muted" style={{ marginTop: 0 }}>
                This tenant is enabled but hasn't been set up yet. Onboard it to create its data
                plane and start adding connections.
              </p>
              <button className="btn btn-solid" disabled={busy}
                onClick={() => run(() => call("onboard", { method: "POST" }), "Tenant onboarded.")}>
                Onboard tenant
              </button>
            </>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              This tenant isn't enabled — contact us to get it provisioned.
            </p>
          )}
        </section>
      )}

      {/* Data-plane form */}
      {onboarded && record && (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Data plane</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <label className="muted" style={{ fontSize: 12 }}>Foundry project endpoint</label>
            <input className="acct-btn" style={{ cursor: "text" }} placeholder="https://…"
              value={dp.foundry_project_endpoint || ""}
              onChange={(e) => setDp({ ...dp, foundry_project_endpoint: e.target.value })} />
            <label className="muted" style={{ fontSize: 12 }}>Foundry model</label>
            <input className="acct-btn" style={{ cursor: "text" }} placeholder="gpt-5-mini"
              value={dp.foundry_model || ""}
              onChange={(e) => setDp({ ...dp, foundry_model: e.target.value })} />
            <label className="muted" style={{ fontSize: 12 }}>Azure Search endpoint</label>
            <input className="acct-btn" style={{ cursor: "text" }} placeholder="https://….search.windows.net"
              value={dp.azure_search_endpoint || ""}
              onChange={(e) => setDp({ ...dp, azure_search_endpoint: e.target.value })} />
            <label className="muted" style={{ fontSize: 12 }}>Azure Search knowledge base</label>
            <input className="acct-btn" style={{ cursor: "text" }} placeholder="knowledge base name"
              value={dp.azure_search_knowledge_base || ""}
              onChange={(e) => setDp({ ...dp, azure_search_knowledge_base: e.target.value })} />
          </div>
          <div style={{ marginTop: 12 }}>
            <button className="btn btn-solid" disabled={busy}
              onClick={() => run(() => call("config", {
                method: "PUT",
                body: JSON.stringify({
                  foundry_project_endpoint: dp.foundry_project_endpoint || "",
                  foundry_model: dp.foundry_model || "",
                  azure_search_endpoint: dp.azure_search_endpoint || "",
                  azure_search_knowledge_base: dp.azure_search_knowledge_base || "",
                }),
              }), "Data plane saved.")}>
              Save
            </button>
          </div>
        </section>
      )}

      {/* Connections table + add form */}
      {onboarded && (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Connections</h3>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="evals">
              <thead>
                <tr>
                  <th>Kind</th><th>Label</th><th>Reference</th>
                  <th>Read</th><th>Write</th><th>Enabled</th><th></th>
                </tr>
              </thead>
              <tbody>
                {connections.length === 0 && <tr><td colSpan={7} className="muted">No connections yet.</td></tr>}
                {connections.map((c) => (
                  <tr key={c.id}>
                    <td><span className="pill neutral">{c.kind}</span></td>
                    <td>{c.label}</td>
                    <td className="muted">{c.foundry_connection_id || c.keyvault_ref || "—"}</td>
                    <td><span className="pill ok">{c.min_role_read || "—"}</span></td>
                    <td><span className="pill ok">{c.min_role_write || "—"}</span></td>
                    <td><span className={`pill ${c.enabled ? "ok" : "bad"}`}>{c.enabled ? "yes" : "no"}</span></td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="acct-btn" disabled={busy} onClick={() => editConn(c)}>Edit</button>
                      <button className="acct-btn" disabled={busy} style={{ marginLeft: 6 }}
                        onClick={() => { if (confirm(`Delete connection ${c.label || c.id}?`)) run(() => call(`connections/${c.id}`, { method: "DELETE" }), "Connection deleted."); }}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 16 }}>
            <h4 style={{ margin: "0 0 8px" }}>{form.id ? "Edit connection" : "Add connection"}</h4>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Kind</label>
                <select className="acct-btn" style={{ width: "100%" }} value={form.kind}
                  onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                  {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
              </div>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Label</label>
                <input className="acct-btn" style={{ width: "100%", cursor: "text" }} placeholder="Display label"
                  value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
              </div>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Foundry connection id</label>
                <input className="acct-btn" style={{ width: "100%", cursor: "text" }} placeholder="foundry connection id"
                  value={form.foundry_connection_id} onChange={(e) => setForm({ ...form, foundry_connection_id: e.target.value })} />
              </div>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Key Vault reference</label>
                <input className="acct-btn" style={{ width: "100%", cursor: "text" }} placeholder="keyvault secret ref"
                  value={form.keyvault_ref} onChange={(e) => setForm({ ...form, keyvault_ref: e.target.value })} />
              </div>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Min role (read)</label>
                <select className="acct-btn" style={{ width: "100%" }} value={form.min_role_read}
                  onChange={(e) => setForm({ ...form, min_role_read: e.target.value })}>
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Min role (write)</label>
                <select className="acct-btn" style={{ width: "100%" }} value={form.min_role_write}
                  onChange={(e) => setForm({ ...form, min_role_write: e.target.value })}>
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 12, alignItems: "center" }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 14 }}>
                <input type="checkbox" checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                Enabled
              </label>
              <div style={{ flex: 1 }} />
              {form.id && (
                <button className="acct-btn" disabled={busy} onClick={() => setForm({ ...emptyForm })}>
                  Cancel
                </button>
              )}
              <button className="btn btn-solid" disabled={busy || !form.label}
                onClick={() => run(() => call("connections", {
                  method: "POST",
                  body: JSON.stringify({
                    ...(form.id ? { id: form.id } : {}),
                    kind: form.kind,
                    label: form.label,
                    foundry_connection_id: form.foundry_connection_id || undefined,
                    keyvault_ref: form.keyvault_ref || undefined,
                    min_role_read: form.min_role_read,
                    min_role_write: form.min_role_write,
                    enabled: form.enabled,
                  }),
                }), form.id ? "Connection updated." : "Connection added.").then(() => setForm({ ...emptyForm }))}>
                {form.id ? "Update" : "Add"} connection
              </button>
            </div>
            <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              No secret is entered here — store the secret in Foundry or Key Vault and reference it
              by id / ref above.
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
