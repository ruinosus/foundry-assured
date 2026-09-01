"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { authedFetch } from "@/lib/auth/api";

type StoredChangeSet = {
  id: string;
  state: string;
  revision: number;
  etag: string;
  content_hash: string;
  content: {
    justification?: string;
    operations?: Array<{ id?: string; operation?: string }>;
  };
};

function responseCode(body: unknown): string {
  if (!body || typeof body !== "object") return "UNKNOWN";
  const error = (body as { error?: unknown }).error;
  return typeof error === "object" && error
    ? String((error as { code?: unknown }).code ?? "UNKNOWN")
    : "UNKNOWN";
}

export function ChangeSetTracer({ areaId, snapshotId }: { areaId: string | null; snapshotId: string | null }) {
  const t = useTranslations("changeset");
  const [lookupId, setLookupId] = useState("");
  const [justification, setJustification] = useState("");
  const [operationId, setOperationId] = useState("draft-operation");
  const [operation, setOperation] = useState("create");
  const [record, setRecord] = useState<StoredChangeSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const headers = () => ({ "X-Area-ID": areaId ?? "", "Content-Type": "application/json" });
  const content = () => ({ justification, operations: [{ id: operationId, operation }] });

  const apply = (next: StoredChangeSet) => {
    setRecord(next);
    setLookupId(next.id);
    setJustification(next.content.justification ?? "");
    setOperationId(next.content.operations?.[0]?.id ?? "draft-operation");
    setOperation(next.content.operations?.[0]?.operation ?? "create");
  };

  const create = async () => {
    if (!areaId || !snapshotId) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await authedFetch("/api/authoring/changesets", {
        method: "POST",
        headers: { ...headers(), "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ source: "manual", base_snapshot_id: snapshotId, content: content() }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(responseCode(body));
      apply(body);
      setNotice(t("created"));
    } catch (caught) {
      setNotice(t("failed", { code: caught instanceof Error ? caught.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const load = async () => {
    if (!areaId || !lookupId) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await authedFetch(`/api/authoring/changesets/${encodeURIComponent(lookupId)}`, {
        cache: "no-store",
        headers: headers(),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(responseCode(body));
      apply(body);
      setNotice(t("loaded"));
    } catch (caught) {
      setNotice(t("failed", { code: caught instanceof Error ? caught.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!areaId || !record) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await authedFetch(`/api/authoring/changesets/${encodeURIComponent(record.id)}`, {
        method: "PATCH",
        headers: { ...headers(), "If-Match": record.etag },
        body: JSON.stringify({ content: content() }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(responseCode(body));
      apply(body);
      setNotice(t("saved"));
    } catch (caught) {
      setNotice(t("failed", { code: caught instanceof Error ? caught.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="changeset-tracer" aria-labelledby="changeset-title">
      <header>
        <div>
          <h3 id="changeset-title">{t("title")}</h3>
          <p>{t("subtitle")}</p>
        </div>
        {record && <span className="changeset-revision">{t("revision", { revision: record.revision })}</span>}
      </header>

      <div className="changeset-lookup">
        <label><span>{t("id")}</span><input value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder={t("idPlaceholder")} /></label>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy || !areaId || !lookupId}>{t("load")}</button>
      </div>

      <div className="changeset-fields">
        <label className="changeset-justification"><span>{t("justification")}</span><textarea value={justification} onChange={(event) => setJustification(event.target.value)} rows={3} maxLength={2000} /></label>
        <label><span>{t("operationId")}</span><input value={operationId} onChange={(event) => setOperationId(event.target.value)} maxLength={63} /></label>
        <label><span>{t("operation")}</span><select value={operation} onChange={(event) => setOperation(event.target.value)}><option value="create">{t("operations.create")}</option><option value="revise">{t("operations.revise")}</option><option value="deprecate">{t("operations.deprecate")}</option></select></label>
      </div>

      <footer>
        <div>{record && <><code>{record.content_hash.slice(0, 12)}</code><span>{record.state}</span></>}</div>
        <div className="changeset-actions">
          <button type="button" className="btn" onClick={() => void create()} disabled={busy || !areaId || !snapshotId || !justification}>{t("create")}</button>
          <button type="button" className="btn primary" onClick={() => void save()} disabled={busy || !record || !justification}>{t("save")}</button>
        </div>
      </footer>
      {notice && <p className="changeset-notice" role="status">{notice}</p>}
    </section>
  );
}