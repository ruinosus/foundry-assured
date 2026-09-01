"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { AREA_SELECTION_EVENT } from "@/lib/area-selection";
import { authedFetch } from "@/lib/auth/api";

interface Connection { id: string; label: string; enabled?: boolean }
interface RegistryTool { name: string; status: "pass" | "block"; effectiveEffect: string }
interface RegistryBinding {
  id: string;
  name: string;
  connectionId: string;
  risk: "read" | "write";
  source: { name?: string; id?: string; resolvedVersion?: string };
  snapshot: { id: string; hash: string };
  tools: RegistryTool[];
  status: "pending_review" | "blocked" | "active";
  reasons: string[];
  revision: number;
}

const emptyForm = {
  id: "",
  name: "",
  connectionId: "",
  risk: "read" as "read" | "write",
  toolboxName: "",
  toolboxVersion: "",
  snapshotId: "",
  snapshotHash: "",
  tools: "",
};

async function call(path: string, init?: RequestInit) {
  const response = await authedFetch(`/api/authoring/${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error?.code || `HTTP_${response.status}`);
  return body;
}

export function RegistriesView() {
  const t = useTranslations("registries");
  const [items, setItems] = useState<RegistryBinding[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [form, setForm] = useState({ ...emptyForm });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setNotice(null);
    try {
      const [registries, connectionResponse] = await Promise.all([
        call("registry-bindings"),
        authedFetch("/api/tenant/connections").then(async (response) => {
          const body = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(body.detail || `HTTP_${response.status}`);
          return body;
        }),
      ]);
      setItems(registries.items ?? []);
      setConnections((connectionResponse.connections ?? []).filter((item: Connection) => item.enabled !== false));
    } catch (error) {
      setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    }
  }, [t]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) void load();
    });
    const onArea = () => void load();
    window.addEventListener(AREA_SELECTION_EVENT, onArea);
    return () => {
      active = false;
      window.removeEventListener(AREA_SELECTION_EVENT, onArea);
    };
  }, [load]);

  const edit = (item: RegistryBinding) => {
    setForm({
      id: item.id,
      name: item.name,
      connectionId: item.connectionId,
      risk: item.risk,
      toolboxName: item.source.name ?? "",
      toolboxVersion: item.source.resolvedVersion ?? "",
      snapshotId: item.snapshot.id,
      snapshotHash: item.snapshot.hash,
      tools: item.tools.map((tool) => tool.name).join(", "),
    });
  };

  const save = async () => {
    const current = items.find((item) => item.id === form.id);
    setBusy(true);
    setNotice(null);
    try {
      await call("registry-bindings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: form.id,
          name: form.name,
          connectionId: form.connectionId,
          risk: form.risk,
          binding: {
            toolbox: { name: form.toolboxName, version: form.toolboxVersion },
            tools: form.tools.split(",").map((tool) => tool.trim()).filter(Boolean),
            reviewedSnapshot: { id: form.snapshotId, hash: form.snapshotHash },
          },
          ...(current ? { expectedRevision: current.revision } : {}),
        }),
      });
      setForm({ ...emptyForm });
      setNotice(t("saved"));
      await load();
    } catch (error) {
      setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const refresh = async (id: string) => {
    setBusy(true);
    try {
      await call(`registry-bindings/${encodeURIComponent(id)}/refresh`, { method: "POST" });
      await load();
    } catch (error) {
      setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const valid = form.id && form.name && form.connectionId && form.toolboxName && form.toolboxVersion
    && form.snapshotId && /^[a-f0-9]{64}$/.test(form.snapshotHash) && form.tools.trim();

  return (
    <div className="registries-page">
      <header className="registries-heading">
        <div><h1>{t("title")}</h1><p>{t("subtitle")}</p></div>
        <span className="catalog-status">{t("count", { count: items.length })}</span>
      </header>

      {notice && <p className="notice notice-body" role="status">{notice}</p>}

      <div className="registries-layout">
        <section className="registries-list" aria-label={t("listLabel")}> 
          {items.length === 0 && <div className="catalog-state"><div><strong>{t("empty")}</strong><p>{t("emptyBody")}</p></div></div>}
          {items.map((item) => (
            <article className="registry-item" key={item.id}>
              <header><div><strong>{item.name}</strong><code>{item.id}</code></div><span className={`catalog-status ${item.status === "blocked" ? "unavailable" : "available"}`}>{t(`status.${item.status}`)}</span></header>
              <dl className="registry-facts">
                <div><dt>{t("source")}</dt><dd>{item.source.name ?? item.source.id}@{item.source.resolvedVersion ?? "-"}</dd></div>
                <div><dt>{t("connection")}</dt><dd>{item.connectionId}</dd></div>
                <div><dt>{t("risk")}</dt><dd>{t(`riskValue.${item.risk}`)}</dd></div>
                <div><dt>{t("snapshot")}</dt><dd>{item.snapshot.id}</dd></div>
              </dl>
              <div className="registry-tools">{item.tools.map((tool) => <span className={tool.status === "pass" ? "allowed" : "denied"} key={tool.name}>{tool.name} · {tool.effectiveEffect}</span>)}</div>
              {item.reasons.length > 0 && <p className="registry-reasons">{item.reasons.join(" · ")}</p>}
              <footer><button className="btn" type="button" onClick={() => edit(item)}>{t("edit")}</button><button className="btn" type="button" disabled={busy} onClick={() => void refresh(item.id)}>{t("refresh")}</button></footer>
            </article>
          ))}
        </section>

        <section className="registry-form">
          <header><h2>{form.id && items.some((item) => item.id === form.id) ? t("editTitle") : t("newTitle")}</h2><p>{t("formBody")}</p></header>
          <div className="registry-fields">
            <label>{t("id")}<input value={form.id} maxLength={63} onChange={(event) => setForm({ ...form, id: event.target.value })} /></label>
            <label>{t("name")}<input value={form.name} maxLength={120} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            <label>{t("connection")}<select value={form.connectionId} onChange={(event) => setForm({ ...form, connectionId: event.target.value })}><option value="">{t("chooseConnection")}</option>{connections.map((connection) => <option key={connection.id} value={connection.id}>{connection.label} · {connection.id}</option>)}</select></label>
            <label>{t("risk")}<select value={form.risk} onChange={(event) => setForm({ ...form, risk: event.target.value as "read" | "write" })}><option value="read">{t("riskValue.read")}</option><option value="write">{t("riskValue.write")}</option></select></label>
            <label>{t("toolbox")}<input value={form.toolboxName} maxLength={63} onChange={(event) => setForm({ ...form, toolboxName: event.target.value })} /></label>
            <label>{t("version")}<input value={form.toolboxVersion} maxLength={64} onChange={(event) => setForm({ ...form, toolboxVersion: event.target.value })} /></label>
            <label>{t("snapshot")}<input value={form.snapshotId} maxLength={128} onChange={(event) => setForm({ ...form, snapshotId: event.target.value })} /></label>
            <label className="wide">{t("hash")}<input className="t-mono" value={form.snapshotHash} maxLength={64} onChange={(event) => setForm({ ...form, snapshotHash: event.target.value.toLowerCase() })} /></label>
            <label className="wide">{t("tools")}<textarea rows={3} value={form.tools} onChange={(event) => setForm({ ...form, tools: event.target.value })} /></label>
          </div>
          <p className="registry-guardrail">{t("guardrail")}</p>
          <footer><button className="btn" type="button" onClick={() => setForm({ ...emptyForm })}>{t("clear")}</button><button className="btn btn-solid" type="button" disabled={busy || !valid} onClick={() => void save()}>{busy ? t("saving") : t("save")}</button></footer>
        </section>
      </div>
    </div>
  );
}