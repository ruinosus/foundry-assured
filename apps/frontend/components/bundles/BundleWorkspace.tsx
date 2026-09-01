"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { AREA_SELECTION_EVENT } from "@/lib/area-selection";
import { authedFetch } from "@/lib/auth/api";
import { canApprove, canAuthor, useMyRoles } from "@/lib/auth/roles";
import { diffWords } from "@/lib/text-diff";

interface BundleDocument {
  key: string;
  type: string;
  id: string;
  revision: string;
  operation: string;
  text: string;
}
interface BundleProjection {
  id: string;
  state: "draft" | "submitted" | "approved" | "rejected";
  revision: number;
  etag: string;
  content_hash: string;
  updated_at: string;
  bundle: BundleDocument;
  documents: BundleDocument[];
  dependencies: Array<{ from: string; to: string; source: string; status: string }>;
  validations: Array<{ id: string; status: string; reason: string }>;
  content: { operations: Array<Record<string, unknown>>; gaps?: unknown[] };
  canSubmit: boolean;
}
interface DecisionRecord {
  id: string;
  revision: number;
  content_hash: string;
  decision: "approve" | "reject";
  reason: string;
  approver_id: string;
  correlation_id: string;
  created_at: string;
}

async function request(path: string, init?: RequestInit) {
  const response = await authedFetch(`/api/authoring/${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error?.code || body.detail || `HTTP_${response.status}`);
    Object.assign(error, { status: response.status });
    throw error;
  }
  return body;
}

function textField(record: Record<string, unknown>, field: string, fallback: string) {
  return typeof record[field] === "string" ? record[field] : fallback;
}

export function BundleWorkspace({ bundleId, editing = false }: Readonly<{ bundleId?: string; editing?: boolean }>) {
  const t = useTranslations("bundles");
  const router = useRouter();
  const search = useSearchParams();
  const roles = useMyRoles();
  const [items, setItems] = useState<BundleProjection[]>([]);
  const [bundle, setBundle] = useState<BundleProjection | null>(null);
  const [previous, setPrevious] = useState<BundleProjection | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [activeKey, setActiveKey] = useState(search.get("document") ?? "");
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setNotice(null);
    try {
      if (!bundleId) {
        const result = await request("bundles");
        setItems(result.items ?? []);
        return;
      }
      const revision = search.get("revision");
      const revisionQuery = revision ? `?revision=${revision}` : "";
      const current: BundleProjection = await request(`bundles/${encodeURIComponent(bundleId)}${revisionQuery}`);
      setBundle(current);
      const decisionHistory = await request(`changesets/${encodeURIComponent(bundleId)}/decisions`);
      setDecisions(decisionHistory.items ?? []);
      const selected = current.documents.find((document) => document.key === (search.get("document") ?? activeKey)) ?? current.bundle;
      setActiveKey(selected.key);
      setDraft(selected.text);
      if (current.revision > 1) {
        setPrevious(await request(`bundles/${encodeURIComponent(bundleId)}?revision=${current.revision - 1}`));
      } else setPrevious(null);
    } catch (error) {
      setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    }
  }, [activeKey, bundleId, search, t]);

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

  const selectDocument = (document: BundleDocument) => {
    setActiveKey(document.key);
    setDraft(document.text);
    const query = new URLSearchParams(search.toString());
    query.set("revision", String(bundle?.revision ?? 1));
    query.set("document", document.key);
    router.replace(`/bundles/${bundleId}${editing ? "/edit" : ""}?${query}`);
  };

  const save = async () => {
    if (!bundle) return;
    setBusy(true); setConflict(false); setNotice(null);
    const operations = bundle.content.operations.map((operation) => {
      const document = bundle.documents.find((item) => item.text === operation.document);
      return document?.key === activeKey ? { ...operation, document: draft } : operation;
    });
    try {
      const updated = await request(`bundles/${bundle.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "If-Match": bundle.etag },
        body: JSON.stringify({ content: { ...bundle.content, operations } }),
      });
      setBundle(updated);
      router.replace(`/bundles/${bundle.id}/edit?revision=${updated.revision}&document=${encodeURIComponent(activeKey)}`);
      setNotice(t("saved"));
    } catch (error) {
      if ((error as Error & { status?: number }).status === 412) setConflict(true);
      else setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    } finally { setBusy(false); }
  };

  const transition = async (action: "submit" | "revisions") => {
    if (!bundle) return;
    setBusy(true); setConflict(false);
    try {
      const updated = await request(`bundles/${bundle.id}/${action}`, { method: "POST", headers: { "If-Match": bundle.etag } });
      setBundle(updated);
      router.replace(`/bundles/${bundle.id}${action === "revisions" ? "/edit" : ""}?revision=${updated.revision}`);
    } catch (error) {
      if ((error as Error & { status?: number }).status === 412) setConflict(true);
      else setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    } finally { setBusy(false); }
  };

  const decide = async (decision: "approve" | "reject") => {
    if (!bundle || !reason.trim()) return;
    setBusy(true); setNotice(null);
    try {
      if (decision === "approve") {
        await request(`changesets/${bundle.id}/validations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revision: bundle.revision, phase: "approval" }),
        });
      }
      await request(`changesets/${bundle.id}/decisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          revision: bundle.revision,
          content_hash: bundle.content_hash,
          decision,
          reason: reason.trim(),
        }),
      });
      setReason("");
      await load();
    } catch (error) {
      setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    } finally { setBusy(false); }
  };

  if (!bundleId) return <div className="bundle-page"><header className="bundle-heading"><div><h1>{t("title")}</h1><p>{t("subtitle")}</p></div><span className="catalog-status">{t("count", { count: items.length })}</span></header>{notice && <p className="notice">{notice}</p>}<section className="bundle-catalog">{items.length === 0 ? <div className="catalog-state"><div><strong>{t("empty")}</strong><p>{t("emptyBody")}</p></div></div> : items.map((item) => <Link className="bundle-row" href={`/bundles/${item.id}?revision=${item.revision}`} key={item.id}><div><strong>{item.bundle.id}</strong><code>{item.id}</code></div><span>{t("revision", { revision: item.revision })}</span><span className={`catalog-status ${item.state === "draft" ? "unavailable" : "available"}`}>{t(`state.${item.state}`)}</span></Link>)}</section></div>;

  if (!bundle) return <div className="catalog-state"><div><strong>{notice ?? t("loading")}</strong></div></div>;
  const active = bundle.documents.find((document) => document.key === activeKey) ?? bundle.bundle;
  const before = previous?.documents.find((document) => document.type === active.type && document.id === active.id)?.text ?? "";
  const diff = diffWords(before, editing ? draft : active.text);
  const operations = bundle.content.operations;
  const sources = Array.from(new Set(operations.flatMap((operation) => {
    const evidence = Array.isArray(operation.evidence) ? operation.evidence : [];
    return evidence.flatMap((item) => typeof item === "object" && item !== null && typeof (item as Record<string, unknown>).source === "string" ? [(item as Record<string, string>).source] : []);
  })));
  const gaps = Array.isArray(bundle.content.gaps) ? bundle.content.gaps.filter((gap): gap is Record<string, unknown> => typeof gap === "object" && gap !== null) : [];
  const currentDecision = decisions.find((item) => item.revision === bundle.revision && item.content_hash === bundle.content_hash);

  return <div className="bundle-page"><header className="bundle-heading"><div><Link className="back-link" href="/bundles">{t("back")}</Link><h1>{bundle.bundle.id}</h1><p>{t("revisionState", { revision: bundle.revision, state: t(`state.${bundle.state}`) })}</p><code className="bundle-hash">sha256:{bundle.content_hash}</code></div><div className="bundle-actions">{canAuthor(roles) && !editing && bundle.state === "draft" && <Link className="btn" href={`/bundles/${bundle.id}/edit?revision=${bundle.revision}&document=${encodeURIComponent(active.key)}`}>{t("edit")}</Link>}{canAuthor(roles) && bundle.state === "draft" && <button type="button" className="btn btn-solid" disabled={busy || !bundle.canSubmit} onClick={() => void transition("submit")}>{t("submit")}</button>}{canAuthor(roles) && bundle.state === "submitted" && <button type="button" className="btn" disabled={busy} onClick={() => void transition("revisions")}>{t("newRevision")}</button>}</div></header>
  {notice && <p className="notice">{notice}</p>}{conflict && <div className="catalog-state blocked"><div><strong>{t("conflict")}</strong><p>{t("conflictBody")}</p></div><button type="button" className="btn" onClick={() => void load()}>{t("rebase")}</button></div>}
  {!editing && <section className="bundle-review" aria-label={t("reviewSummary")}><div><h2>{t("impact")}</h2><ul>{operations.map((operation) => <li key={textField(operation, "id", JSON.stringify(operation))}><strong>{textField(operation, "operation", t("change"))}</strong> {textField(operation, "document_type", t("document"))} · {textField(operation, "id", t("document"))}</li>)}</ul></div><div><h2>{t("sources")}</h2>{sources.length ? <ul>{sources.map((source) => <li key={source}>{source}</li>)}</ul> : <p>{t("noSources")}</p>}</div><div><h2>{t("gaps")}</h2>{gaps.length ? <ul>{gaps.map((gap) => <li key={JSON.stringify(gap)}>{textField(gap, "reason", textField(gap, "capability", t("gapDeclared")))}</li>)}</ul> : <p>{t("noGaps")}</p>}</div><div><h2>{t("compensation")}</h2>{gaps.length ? <ul>{gaps.map((gap) => <li key={JSON.stringify(gap)}>{textField(gap, "compensation", t("compensationMissing"))}</li>)}</ul> : <p>{t("compensationNone")}</p>}</div></section>}
  {!editing && bundle.state === "submitted" && canApprove(roles) && <section className="bundle-decision" aria-labelledby="bundle-decision-title"><div><span>{t("humanDecision")}</span><h2 id="bundle-decision-title">{t("decisionTitle", { revision: bundle.revision })}</h2><p>{t("decisionBody")}</p></div><label><span>{t("reason")}</span><textarea value={reason} maxLength={1000} onChange={(event) => setReason(event.target.value)} placeholder={t("reasonPlaceholder")} /></label><div className="bundle-decision-actions"><button type="button" className="btn btn-danger" disabled={busy || !reason.trim()} onClick={() => void decide("reject")}>{t("reject")}</button><button type="button" className="btn btn-solid" disabled={busy || !reason.trim()} onClick={() => void decide("approve")}>{t("approve")}</button></div></section>}
  {currentDecision && <section className={`bundle-decision-record ${currentDecision.decision}`}><div><span>{t("recordedDecision")}</span><strong>{t(`decision.${currentDecision.decision}`)}</strong></div><p>{currentDecision.reason}</p><dl><div><dt>{t("actor")}</dt><dd>{currentDecision.approver_id}</dd></div><div><dt>{t("correlation")}</dt><dd><code>{currentDecision.correlation_id}</code></dd></div></dl></section>}
  <div className="bundle-workspace"><aside className="bundle-tree" aria-label={t("tree")}><strong>{t("documents")}</strong>{bundle.documents.map((document) => <button type="button" className={document.key === active.key ? "selected" : ""} key={document.key} onClick={() => selectDocument(document)}><span>{document.type}</span><b>{document.id}</b><small>@{document.revision}</small></button>)}</aside>
  <main className="bundle-document"><header><div><span>{active.type}</span><h2>{active.id}</h2></div><code>{active.key}</code></header>{editing ? <textarea aria-label={t("documentSource")} value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} /> : <pre>{active.text}</pre>}{editing && <footer><button type="button" className="btn btn-solid" disabled={busy || draft === active.text} onClick={() => void save()}>{t("save")}</button></footer>}</main>
  <aside className="bundle-inspector"><section><h3>{t("validations")}</h3>{bundle.validations.map((check) => <div className={`bundle-check ${check.status}`} key={check.id}><strong>{check.id}</strong><p>{check.reason}</p></div>)}</section><section><h3>{t("dependencies")}</h3>{bundle.dependencies.length === 0 ? <p className="muted">{t("none")}</p> : bundle.dependencies.filter((dependency) => dependency.from === active.key).map((dependency) => <div className="bundle-dependency" key={`${dependency.from}-${dependency.to}`}><code>{dependency.to}</code><span>{dependency.source}</span></div>)}</section><section><h3>{t("diff")}</h3>{diff.truncated ? <p>{t("diffLarge")}</p> : <div className="bundle-diff">{diff.parts.map((part, index) => <span className={part.op} key={`${part.op}-${index}`}>{part.text}</span>)}</div>}</section></aside></div></div>;
}
