"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { authedFetch } from "@/lib/auth/api";

type AreaStatus = "active" | "suspended";

interface Area {
  id: string;
  name: string;
  entra_group_ids: string[];
  status: AreaStatus;
  revision: number;
}

interface AreaDraft {
  id: string;
  name: string;
  groups: string;
}

const emptyDraft = (): AreaDraft => ({ id: crypto.randomUUID(), name: "", groups: "" });
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function parseGroups(value: string): string[] {
  const groups = value.split(/[\s,]+/).map((group) => group.trim()).filter(Boolean);
  if (groups.some((group) => !UUID_PATTERN.test(group))) throw new Error("INVALID_GROUP_ID");
  return [...new Set(groups)];
}

async function call(path: string, init?: RequestInit): Promise<{ data: unknown; etag: string | null }> {
  const response = await authedFetch(`/api/tenant/${path}`, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data === "object" && data && "detail" in data ? String(data.detail) : `error ${response.status}`;
    const error = new Error(detail);
    error.name = String(response.status);
    throw error;
  }
  return { data, etag: response.headers.get("etag") };
}

export function Areas() {
  const t = useTranslations("areas");
  const tc = useTranslations("common");
  const [areas, setAreas] = useState<Area[]>([]);
  const [draft, setDraft] = useState<AreaDraft>(emptyDraft);
  const [editing, setEditing] = useState<Area | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { data } = await call("areas");
      const payload = data as { areas?: Area[] };
      setAreas(payload.areas ?? []);
    } catch (cause) {
      setError((cause as Error).message);
    }
  }, []);

  useEffect(() => {
    let active = true;
    call("areas")
      .then(({ data }) => {
        if (active) setAreas((data as { areas?: Area[] }).areas ?? []);
      })
      .catch((cause) => {
        if (active) setError((cause as Error).message);
      });
    return () => {
      active = false;
    };
  }, []);

  const run = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await operation();
      setMessage(success);
      setEditing(null);
      await load();
    } catch (cause) {
      const failure = cause as Error;
      if (failure.name === "412") {
        setEditing(null);
        await load();
      }
      setError(failure.name === "412" ? t("revisionConflict") : failure.message === "INVALID_GROUP_ID" ? t("invalidGroup") : failure.message);
    } finally {
      setBusy(false);
    }
  };

  const create = () => run(async () => {
    await call("areas", {
      method: "POST",
      body: JSON.stringify({ id: draft.id, name: draft.name.trim(), entra_group_ids: parseGroups(draft.groups) }),
    });
    setDraft(emptyDraft());
  }, t("created"));

  const update = (
    area: Area,
    changes: Partial<Pick<Area, "name" | "entra_group_ids" | "status">> | (() => Partial<Pick<Area, "name" | "entra_group_ids" | "status">>),
    success: string,
  ) => run(
    () => call(`areas/${area.id}`, {
      method: "PATCH",
      headers: { "If-Match": `"${area.revision}"` },
      body: JSON.stringify(typeof changes === "function" ? changes() : changes),
    }),
    success,
  );

  return (
    <div className="stack area-admin">
      <header>
        <h1>{t("title")}</h1>
        <p className="muted t-sm">{t("subtitle")}</p>
      </header>

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {message && <div className="notice notice-success" role="status">{message}</div>}

      <section className="card">
        <div className="row area-section-heading">
          <div className="grow">
            <h3>{t("configured")}</h3>
            <p className="muted t-xs">{t("authorityNote")}</p>
          </div>
          <button className="btn" type="button" disabled={busy} onClick={load}>{tc("refresh")}</button>
        </div>
        <div className="table-wrap">
          <table className="tbl area-table">
            <thead><tr><th>{t("name")}</th><th>{t("groups")}</th><th>{t("status")}</th><th>{t("revision")}</th><th></th></tr></thead>
            <tbody>
              {areas.length === 0 && <tr><td colSpan={5} className="muted">{t("empty")}</td></tr>}
              {areas.map((area) => (
                <tr key={area.id}>
                  <td><strong>{area.name}</strong><div className="muted t-mono">{area.id}</div></td>
                  <td>{area.entra_group_ids.length}</td>
                  <td><span className={`pill ${area.status === "active" ? "ok" : "neutral"}`}>{t(area.status)}</span></td>
                  <td className="t-mono">{area.revision}</td>
                  <td className="right nowrap">
                    <button className="btn" type="button" disabled={busy} onClick={() => setEditing(area)}>{tc("edit")}</button>
                    <button
                      className="btn"
                      type="button"
                      disabled={busy}
                      onClick={() => update(area, { status: area.status === "active" ? "suspended" : "active" }, area.status === "active" ? t("suspendedMessage") : t("reactivatedMessage"))}
                    >
                      {area.status === "active" ? t("suspend") : t("reactivate")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="area-mobile-list">
          {areas.length === 0 && <p className="muted">{t("empty")}</p>}
          {areas.map((area) => (
            <article className="area-mobile-item" key={area.id}>
              <div className="row-tight">
                <strong className="grow">{area.name}</strong>
                <span className={`pill ${area.status === "active" ? "ok" : "neutral"}`}>{t(area.status)}</span>
              </div>
              <div className="muted t-mono area-mobile-id">{area.id}</div>
              <div className="muted t-xs">{t("groupCount", { count: area.entra_group_ids.length })} · {t("revisionValue", { revision: area.revision })}</div>
              <div className="row-tight">
                <button className="btn grow" type="button" disabled={busy} onClick={() => setEditing(area)}>{tc("edit")}</button>
                <button
                  className="btn grow"
                  type="button"
                  disabled={busy}
                  onClick={() => update(area, { status: area.status === "active" ? "suspended" : "active" }, area.status === "active" ? t("suspendedMessage") : t("reactivatedMessage"))}
                >
                  {area.status === "active" ? t("suspend") : t("reactivate")}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      {editing && (
        <section className="card">
          <h3>{t("editTitle", { name: editing.name })}</h3>
          <div className="grid g2 area-form-grid">
            <label className="field">
              <span className="field-label">{t("name")}</span>
              <input className="input" value={editing.name} maxLength={120} onChange={(event) => setEditing({ ...editing, name: event.target.value })} />
            </label>
            <label className="field">
              <span className="field-label">{t("groupIds")}</span>
              <textarea className="input area-groups" value={editing.entra_group_ids.join("\n")} onChange={(event) => setEditing({ ...editing, entra_group_ids: event.target.value.split(/\s+/).filter(Boolean) })} />
            </label>
          </div>
          <div className="row">
            <button className="btn btn-solid" type="button" disabled={busy || !editing.name.trim()} onClick={() => update(editing, () => ({ name: editing.name.trim(), entra_group_ids: parseGroups(editing.entra_group_ids.join("\n")) }), t("updated"))}>{tc("save")}</button>
            <button className="btn" type="button" disabled={busy} onClick={() => setEditing(null)}>{tc("cancel")}</button>
          </div>
        </section>
      )}

      <section className="card">
        <h3>{t("createTitle")}</h3>
        <div className="grid g2 area-form-grid">
          <label className="field">
            <span className="field-label">{t("name")}</span>
            <input className="input" value={draft.name} maxLength={120} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">{t("groupIds")}</span>
            <textarea className="input area-groups" value={draft.groups} placeholder={t("groupsPlaceholder")} onChange={(event) => setDraft({ ...draft, groups: event.target.value })} />
          </label>
        </div>
        <div className="row">
          <button className="btn btn-solid" type="button" disabled={busy || !draft.name.trim()} onClick={create}>{t("create")}</button>
          <span className="muted t-mono">{draft.id}</span>
        </div>
      </section>
    </div>
  );
}
