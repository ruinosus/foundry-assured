"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { AREA_SELECTION_EVENT, selectedAreaId } from "@/lib/area-selection";
import { reviewedOperations, type ProposedOperation, type ReviewDecision } from "@/lib/authoring/review";
import { authedFetch } from "@/lib/auth/api";
import { useMyIdentity } from "@/lib/auth/roles";

type Proposal = {
  snapshot: { id: string; hash: string; at: string };
  proposal: { id: string; justification: string; operations: ProposedOperation[]; gaps: { capability: string; reason: string }[] } | null;
  gaps: { capability: string; reason: string; status?: string }[];
  published: false;
};

function errorCode(body: unknown): string {
  if (!body || typeof body !== "object") return "UNKNOWN";
  const value = body as { detail?: unknown; error?: { code?: unknown } };
  return String(value.error?.code ?? value.detail ?? "UNKNOWN");
}

export function ChangeSetBuilder({ onCancel }: { onCancel: () => void }) {
  const t = useTranslations("changesetBuilder");
  const identity = useMyIdentity();
  const [area, setArea] = useState<string | null>(() => selectedAreaId());
  const [need, setNeed] = useState("");
  const [result, setResult] = useState<Proposal | null>(null);
  const [decisions, setDecisions] = useState<Record<string, ReviewDecision>>({});
  const [documents, setDocuments] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);

  const areaId = identity?.areas.some((item) => item.id === area) ? area : (identity?.areas[0]?.id ?? null);

  useEffect(() => {
    const onArea = (event: Event) => {
      setArea((event as CustomEvent<string | null>).detail);
      setResult(null);
    };
    window.addEventListener(AREA_SELECTION_EVENT, onArea);
    return () => window.removeEventListener(AREA_SELECTION_EVENT, onArea);
  }, []);

  const propose = async () => {
    if (!areaId || !need.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await authedFetch("/api/proposer/changeset", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Area-ID": areaId },
        body: JSON.stringify({ need: need.trim() }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorCode(body));
      const proposal = body as Proposal;
      setResult(proposal);
      setDecisions({});
      setDocuments(Object.fromEntries((proposal.proposal?.operations ?? []).map((operation) => [operation.id, operation.document])));
      setIdempotencyKey(crypto.randomUUID());
    } catch (caught) {
      setNotice(t("failed", { code: caught instanceof Error ? caught.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!areaId || !result?.proposal || !idempotencyKey) return;
    const operations = reviewedOperations(result.proposal.operations, decisions, documents);
    if (!operations.length || !reviewIsConsistent || !result.proposal.operations.every((operation) => decisions[operation.id]) || result.gaps.some((gap) => gap.status === "missing")) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await authedFetch("/api/proposer/changeset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Area-ID": areaId, "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          proposal: { ...result.proposal, base_version: result.snapshot.id },
          decisions: result.proposal.operations.map((operation) => ({
            operation_id: operation.id,
            decision: decisions[operation.id],
            ...(decisions[operation.id] === "edit" ? { edited_document: documents[operation.id] } : {}),
          })),
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorCode(body));
      setNotice(t("saved", { id: body.id, revision: body.revision }));
    } catch (caught) {
      setNotice(t("failed", { code: caught instanceof Error ? caught.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const operations = result?.proposal?.operations ?? [];
  const reviewed = reviewedOperations(operations, decisions, documents);
  const kept = reviewed.length;
  const keptIds = new Set(reviewed.map((operation) => operation.id));
  const reviewIsConsistent = operations.every(
    (operation) => (decisions[operation.id] === "discard") === !keptIds.has(operation.id),
  );

  return (
    <section className="card wizard changeset-builder">
      <header className="between wizard-head">
        <div><h3 className="section-title">{t("title")}</h3><p className="muted t-sm">{t("subtitle")}</p></div>
        <button type="button" className="btn" onClick={onCancel}>{t("close")}</button>
      </header>

      <div className="changeset-need">
        <label><span className="strong t-sm">{t("need")}</span><textarea className="acct-btn" rows={4} maxLength={2000} value={need} onChange={(event) => setNeed(event.target.value)} placeholder={t("placeholder")} /></label>
        <button type="button" className="btn btn-solid" disabled={busy || !areaId || !need.trim()} onClick={() => void propose()}>{busy ? t("working") : t("propose")}</button>
      </div>

      {notice && <p className="notice notice-body" role="status">{notice}</p>}
      {result && !result.proposal && <div className="notice notice-wait"><p className="notice-title">{t("gapTitle")}</p>{result.gaps.map((gap) => <p className="notice-body" key={gap.capability}>{gap.reason}</p>)}</div>}

      {result?.proposal && <div className="stack-sm">
        <div className="changeset-summary"><div><span className="t-xs muted-line">{t("snapshot")}</span><strong className="t-mono t-sm">{result.snapshot.id}</strong></div><div><span className="t-xs muted-line">{t("documents")}</span><strong>{kept}/{operations.length}</strong></div></div>
        <ol className="changeset-operations">
          {operations.map((operation) => <li key={operation.id} className="changeset-operation">
            <header className="between"><div><span className="pill neutral">{operation.operation}</span><strong>{operation.document_type}</strong></div><span className="t-xs muted-line">{operation.id}</span></header>
            <p className="t-sm">{operation.justification}</p>
            {operation.depends_on.length > 0 && <p className="t-xs muted-line">{t("depends", { ids: operation.depends_on.join(", ") })}</p>}
            <dl className="review">{operation.evidence.map((item) => <div key={`${item.field}:${item.source}`}><dt>{item.field}</dt><dd className="t-xs t-mono">{item.source}</dd></div>)}</dl>
            <div className="segmented" role="group" aria-label={t("decisionFor", { id: operation.id })}>{(["accept", "edit", "discard"] as const).map((decision) => <button type="button" key={decision} className={decisions[operation.id] === decision ? "active" : ""} aria-pressed={decisions[operation.id] === decision} onClick={() => setDecisions((current) => ({ ...current, [operation.id]: decision }))}>{t(`decision.${decision}`)}</button>)}</div>
            {decisions[operation.id] === "edit" && <label><span className="t-xs strong">{t("document")}</span><textarea className="acct-btn t-mono t-xs" rows={12} value={documents[operation.id] ?? operation.document} onChange={(event) => setDocuments((current) => ({ ...current, [operation.id]: event.target.value }))} /></label>}
            {decisions[operation.id] !== "edit" && <details className="wizard-doc"><summary className="t-xs">{t("inspect")}</summary><pre className="doc-preview">{documents[operation.id] ?? operation.document}</pre></details>}
          </li>)}
        </ol>
        {result.gaps.length > 0 && <div className="notice notice-wait"><p className="notice-title">{t("gaps")}</p>{result.gaps.map((gap) => <p className="notice-body" key={gap.capability}>{gap.capability}: {gap.reason}</p>)}</div>}
        <footer className="between changeset-confirm"><p className="t-xs muted-line">{t("inert")}</p><button type="button" className="btn btn-solid" disabled={busy || kept === 0 || !reviewIsConsistent || !operations.every((operation) => decisions[operation.id])} onClick={() => void save()}>{busy ? t("saving") : t("confirm")}</button></footer>
      </div>}
    </section>
  );
}