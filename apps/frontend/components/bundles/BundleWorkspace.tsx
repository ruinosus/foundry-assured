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
  dependencies: Array<{
    from: string;
    to: string;
    source: string;
    status: string;
  }>;
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
interface PublicationRecord {
  id: string;
  changeset_id: string;
  revision: number;
  content_hash: string;
  owner: string;
  provider: "github" | "azure_devops";
  project: string;
  repository: string;
  base_branch: string;
  branch: string;
  pull_request_number: number;
  pull_request_url: string;
  state:
    | "in_progress"
    | "awaiting_approval"
    | "executing"
    | "intervention_required"
    | "pr_open"
    | "merge_confirmed"
    | "materializing"
    | "completed"
    | "compensating"
    | "compensated"
    | "compensation_required"
    | "failed";
  step: string;
  error_code: string;
  updated_at: string;
  etag: string;
  commit_id: string;
  merge_status: string;
}
interface MaterializationJournalEntry {
  position: number;
  operation_id: string;
  kind: string;
  name: string;
  status: string;
  external_id: string;
  version: string;
  error_code: string;
  updated_at: string;
}
interface ToolApprovalRequest {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
}
interface PublicationOutcome {
  publication: PublicationRecord;
  approval: ToolApprovalRequest | null;
  replay: boolean;
}

async function request(path: string, init?: RequestInit) {
  const response = await authedFetch(`/api/authoring/${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(
      body.error?.code || body.detail || `HTTP_${response.status}`,
    );
    Object.assign(error, {
      status: response.status,
      consentUrl: body.error?.consentUrl,
      serverLabel: body.error?.serverLabel,
    });
    throw error;
  }
  return body;
}

function textField(
  record: Record<string, unknown>,
  field: string,
  fallback: string,
) {
  return typeof record[field] === "string" ? record[field] : fallback;
}

function evidenceSource(item: unknown): string[] {
  if (typeof item !== "object" || item === null) return [];
  const source = (item as Record<string, unknown>).source;
  return typeof source === "string" ? [source] : [];
}

function publicationFieldsReady(
  provider: "github" | "azure_devops",
  owner: string,
  project: string,
  repository: string,
) {
  return Boolean(
    owner.trim() &&
      repository.trim() &&
      (provider === "github" || project.trim()),
  );
}

function publicationAdvanceStatus(
  state: string,
  materialized: string,
  stateChanged: string,
) {
  return state === "completed" ? materialized : stateChanged;
}

function journalEntries(value: unknown): MaterializationJournalEntry[] {
  return Array.isArray(value) ? value : [];
}

async function loadPublication(publicationId: string | null): Promise<{
  publication: PublicationRecord | null;
  journal: MaterializationJournalEntry[];
}> {
  if (!publicationId) return { publication: null, journal: [] };
  const publication = await request(
    `publications/${encodeURIComponent(publicationId)}`,
  );
  return { publication, journal: journalEntries(publication.journal) };
}

async function loadPreviousRevision(
  bundleId: string,
  revision: number,
): Promise<BundleProjection | null> {
  if (revision <= 1) return null;
  return request(
    `bundles/${encodeURIComponent(bundleId)}?revision=${revision - 1}`,
  );
}

function useMaterializationAction(
  setBusy: (value: boolean) => void,
  setNotice: (value: string | null) => void,
  setPublication: (value: PublicationRecord | null) => void,
  setJournal: (value: MaterializationJournalEntry[]) => void,
  setStatus: (value: string | null) => void,
) {
  const t = useTranslations("bundles");
  return async (
    currentPublication: PublicationRecord,
    action: "reconcile" | "compensations",
  ) => {
    setBusy(true);
    setNotice(null);
    setStatus({
      reconcile: t("publicationReconciling"),
      compensations: t("publicationCompensating"),
    }[action]);
    try {
      const result = await request(
        `publications/${encodeURIComponent(currentPublication.id)}/${action}`,
        {
          method: "POST",
          headers: {
            "Idempotency-Key": `${action}:${currentPublication.id}:${currentPublication.content_hash}`,
            "If-Match": currentPublication.etag,
          },
        },
      );
      setPublication(result.publication);
      setJournal(journalEntries(result.journal));
      setStatus(
        publicationAdvanceStatus(
          result.publication.state,
          t("publicationMaterialized"),
          t("publicationStateChanged", {
            state: t(`publicationStates.${result.publication.state}`),
          }),
        ),
      );
    } catch (error) {
      setStatus(
        t("publicationFailed", {
          code: error instanceof Error ? error.message : "UNKNOWN",
        }),
      );
    } finally {
      setBusy(false);
    }
  };
}

function MaterializationPanel({
  publication,
  journal,
  busy,
  roles,
  onAdvance,
}: Readonly<{
  publication: PublicationRecord;
  journal: MaterializationJournalEntry[];
  busy: boolean;
  roles: string[] | null;
  onAdvance: (action: "reconcile" | "compensations") => void;
}>) {
  const t = useTranslations("bundles");
  const canReconcile = publication.state === "pr_open" && canApprove(roles);
  const canCompensate =
    publication.state === "compensation_required" && roles?.includes("Admin");

  return (
    <>
      <div className="bundle-publication-result">
        <div>
          <span>{t("publicationPullRequest")}</span>
          <a
            href={publication.pull_request_url}
            target="_blank"
            rel="noreferrer"
          >
            #{publication.pull_request_number} · {publication.owner}/
            {publication.repository}
          </a>
        </div>
        <div>
          <span>{t("publicationBranch")}</span>
          <code>{publication.branch}</code>
        </div>
        <div>
          <span>{t("publicationState")}</span>
          <strong>{t(`publicationStates.${publication.state}`)}</strong>
        </div>
      </div>
      <div className="bundle-decision-actions">
        {canReconcile && (
          <button
            type="button"
            className="btn btn-solid"
            disabled={busy}
            onClick={() => onAdvance("reconcile")}
          >
            {t("publicationReconcile")}
          </button>
        )}
        {canCompensate && (
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => onAdvance("compensations")}
          >
            {t("publicationCompensate")}
          </button>
        )}
      </div>
      <section
        className="bundle-materialization-journal"
        aria-labelledby="materialization-journal-title"
      >
        <h3 id="materialization-journal-title">{t("publicationJournal")}</h3>
        {journal.length === 0 ? (
          <p>{t("publicationJournalEmpty")}</p>
        ) : (
          <ol>
            {journal.map((entry) => (
              <li key={entry.operation_id}>
                <div>
                  <strong>{entry.name}</strong>
                  <span>{entry.kind}</span>
                </div>
                <span>{t(`publicationStepStates.${entry.status}`)}</span>
                {entry.version && <code>{entry.version}</code>}
              </li>
            ))}
          </ol>
        )}
      </section>
    </>
  );
}

function ToolApprovalPanel({
  approval,
  busy,
  onDecision,
}: Readonly<{
  approval: ToolApprovalRequest | null;
  busy: boolean;
  onDecision: (approved: boolean) => void;
}>) {
  const t = useTranslations("bundles");
  if (!approval) return null;
  return (
    <fieldset className="bundle-tool-approval">
      <legend>{t("publicationApprovalTitle")}</legend>
      <div>
        <strong>{approval.tool}</strong>
      </div>
      <pre>{JSON.stringify(approval.arguments, null, 2)}</pre>
      <div className="bundle-decision-actions">
        <button
          type="button"
          className="btn btn-danger"
          disabled={busy}
          onClick={() => onDecision(false)}
        >
          {t("publicationRejectTool")}
        </button>
        <button
          type="button"
          className="btn btn-solid"
          disabled={busy}
          onClick={() => onDecision(true)}
        >
          {t("publicationApproveTool")}
        </button>
      </div>
    </fieldset>
  );
}

export function BundleWorkspace({
  bundleId,
  editing = false,
}: Readonly<{ bundleId?: string; editing?: boolean }>) {
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
  const [publication, setPublication] = useState<PublicationRecord | null>(
    null,
  );
  const [publicationOwner, setPublicationOwner] = useState("");
  const [publicationProvider, setPublicationProvider] = useState<
    "github" | "azure_devops"
  >("github");
  const [publicationProject, setPublicationProject] = useState("");
  const [publicationRepository, setPublicationRepository] = useState("");
  const [publicationBranch, setPublicationBranch] = useState("main");
  const [publicationDirectory, setPublicationDirectory] = useState("okf");
  const [publicationStatus, setPublicationStatus] = useState<string | null>(
    null,
  );
  const [consentUrl, setConsentUrl] = useState<string | null>(null);
  const [toolApproval, setToolApproval] = useState<ToolApprovalRequest | null>(
    null,
  );
  const [publicationJournal, setPublicationJournal] = useState<
    MaterializationJournalEntry[]
  >([]);
  const advanceMaterialization = useMaterializationAction(
    setBusy,
    setNotice,
    setPublication,
    setPublicationJournal,
    setPublicationStatus,
  );

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
      const current: BundleProjection = await request(
        `bundles/${encodeURIComponent(bundleId)}${revisionQuery}`,
      );
      setBundle(current);
      const decisionHistory = await request(
        `changesets/${encodeURIComponent(bundleId)}/decisions`,
      );
      setDecisions(decisionHistory.items ?? []);
      const publicationResult = await loadPublication(
        search.get("publication"),
      );
      setPublication(publicationResult.publication);
      setPublicationJournal(publicationResult.journal);
      const selected =
        current.documents.find(
          (document) => document.key === (search.get("document") ?? activeKey),
        ) ?? current.bundle;
      setActiveKey(selected.key);
      setDraft(selected.text);
      setPrevious(await loadPreviousRevision(bundleId, current.revision));
    } catch (error) {
      setNotice(
        t("failed", {
          code: error instanceof Error ? error.message : "UNKNOWN",
        }),
      );
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
    setBusy(true);
    setConflict(false);
    setNotice(null);
    const operations = bundle.content.operations.map((operation) => {
      const document = bundle.documents.find(
        (item) => item.text === operation.document,
      );
      return document?.key === activeKey
        ? { ...operation, document: draft }
        : operation;
    });
    try {
      const updated = await request(`bundles/${bundle.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "If-Match": bundle.etag,
        },
        body: JSON.stringify({ content: { ...bundle.content, operations } }),
      });
      setBundle(updated);
      router.replace(
        `/bundles/${bundle.id}/edit?revision=${updated.revision}&document=${encodeURIComponent(activeKey)}`,
      );
      setNotice(t("saved"));
    } catch (error) {
      if ((error as Error & { status?: number }).status === 412)
        setConflict(true);
      else
        setNotice(
          t("failed", {
            code: error instanceof Error ? error.message : "UNKNOWN",
          }),
        );
    } finally {
      setBusy(false);
    }
  };

  const transition = async (action: "submit" | "revisions") => {
    if (!bundle) return;
    setBusy(true);
    setConflict(false);
    try {
      const updated = await request(`bundles/${bundle.id}/${action}`, {
        method: "POST",
        headers: { "If-Match": bundle.etag },
      });
      setBundle(updated);
      router.replace(
        `/bundles/${bundle.id}${action === "revisions" ? "/edit" : ""}?revision=${updated.revision}`,
      );
    } catch (error) {
      if ((error as Error & { status?: number }).status === 412)
        setConflict(true);
      else
        setNotice(
          t("failed", {
            code: error instanceof Error ? error.message : "UNKNOWN",
          }),
        );
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decision: "approve" | "reject") => {
    if (!bundle || !reason.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      if (decision === "approve") {
        await request(`changesets/${bundle.id}/validations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            revision: bundle.revision,
            phase: "approval",
          }),
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
      setNotice(
        t("failed", {
          code: error instanceof Error ? error.message : "UNKNOWN",
        }),
      );
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    if (
      !bundle ||
      !publicationFieldsReady(
        publicationProvider,
        publicationOwner,
        publicationProject,
        publicationRepository,
      )
    )
      return;
    setBusy(true);
    setPublicationStatus(t("publicationPreparing"));
    setConsentUrl(null);
    setNotice(null);
    try {
      setPublicationStatus(t("publicationSending"));
      const result: PublicationOutcome = await request("publications", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `${publicationProvider}:${bundle.id}:${bundle.content_hash}`,
        },
        body: JSON.stringify({
          changeset_id: bundle.id,
          provider: publicationProvider,
          revision: bundle.revision,
          content_hash: bundle.content_hash,
          owner: publicationOwner.trim(),
          project:
            publicationProvider === "azure_devops"
              ? publicationProject.trim()
              : undefined,
          repository: publicationRepository.trim(),
          base_branch: publicationBranch.trim(),
          target_directory: publicationDirectory.trim(),
        }),
      });
      setPublication(result.publication);
      setToolApproval(result.approval);
      if (["pr_open", "completed"].includes(result.publication.state)) {
        setPublication(result.publication);
        setPublicationStatus(t("publicationVerified"));
      } else {
        setPublicationStatus(t("publicationApprovalPending"));
      }
    } catch (error) {
      const code = error instanceof Error ? error.message : "UNKNOWN";
      const url = (error as Error & { consentUrl?: unknown }).consentUrl;
      if (typeof url === "string" && url.startsWith("https://"))
        setConsentUrl(url);
      setPublicationStatus(t("publicationFailed", { code }));
    } finally {
      setBusy(false);
    }
  };

  const decidePublicationTool = async (approved: boolean) => {
    if (!bundle || !publication || !toolApproval) return;
    setBusy(true);
    setConsentUrl(null);
    try {
      const result: PublicationOutcome = await request(
        `publications/${encodeURIComponent(publication.id)}/approvals`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            approval_id: toolApproval.id,
            approved,
          }),
        },
      );
      setPublication(result.publication);
      setToolApproval(result.approval);
      if (["pr_open", "completed"].includes(result.publication.state)) {
        setPublicationStatus(t("publicationVerified"));
        const query = new URLSearchParams(search.toString());
        query.set("revision", String(bundle.revision));
        query.set("publication", result.publication.id);
        router.replace(`/bundles/${bundle.id}?${query}`);
      } else {
        setPublicationStatus(t("publicationApprovalPending"));
      }
    } catch (error) {
      const code = error instanceof Error ? error.message : "UNKNOWN";
      const url = (error as Error & { consentUrl?: unknown }).consentUrl;
      if (typeof url === "string" && url.startsWith("https://"))
        setConsentUrl(url);
      const status = (error as Error & { status?: unknown }).status;
      if (status !== 401) setToolApproval(null);
      setPublicationStatus(t("publicationFailed", { code }));
    } finally {
      setBusy(false);
    }
  };

  if (!bundleId)
    return (
      <div className="bundle-page">
        <header className="bundle-heading">
          <div>
            <h1>{t("title")}</h1>
            <p>{t("subtitle")}</p>
          </div>
          <span className="catalog-status">
            {t("count", { count: items.length })}
          </span>
        </header>
        {notice && <p className="notice">{notice}</p>}
        <section className="bundle-catalog">
          {items.length === 0 ? (
            <div className="catalog-state">
              <div>
                <strong>{t("empty")}</strong>
                <p>{t("emptyBody")}</p>
              </div>
            </div>
          ) : (
            items.map((item) => (
              <Link
                className="bundle-row"
                href={`/bundles/${item.id}?revision=${item.revision}`}
                key={item.id}
              >
                <div>
                  <strong>{item.bundle.id}</strong>
                  <code>{item.id}</code>
                </div>
                <span>{t("revision", { revision: item.revision })}</span>
                <span
                  className={`catalog-status ${item.state === "draft" ? "unavailable" : "available"}`}
                >
                  {t(`state.${item.state}`)}
                </span>
              </Link>
            ))
          )}
        </section>
      </div>
    );

  if (!bundle)
    return (
      <div className="catalog-state">
        <div>
          <strong>{notice ?? t("loading")}</strong>
        </div>
      </div>
    );
  const active =
    bundle.documents.find((document) => document.key === activeKey) ??
    bundle.bundle;
  const before =
    previous?.documents.find(
      (document) => document.type === active.type && document.id === active.id,
    )?.text ?? "";
  const diff = diffWords(before, editing ? draft : active.text);
  const operations = bundle.content.operations;
  const sources = Array.from(
    new Set(
      operations.flatMap((operation) => {
        const evidence = Array.isArray(operation.evidence)
          ? operation.evidence
          : [];
        return evidence.flatMap(evidenceSource);
      }),
    ),
  );
  const gaps = Array.isArray(bundle.content.gaps)
    ? bundle.content.gaps.filter(
        (gap): gap is Record<string, unknown> =>
          typeof gap === "object" && gap !== null,
      )
    : [];
  const currentDecision = decisions.find(
    (item) =>
      item.revision === bundle.revision &&
      item.content_hash === bundle.content_hash,
  );

  return (
    <div className="bundle-page">
      <header className="bundle-heading">
        <div>
          <Link className="back-link" href="/bundles">
            {t("back")}
          </Link>
          <h1>{bundle.bundle.id}</h1>
          <p>
            {t("revisionState", {
              revision: bundle.revision,
              state: t(`state.${bundle.state}`),
            })}
          </p>
          <code className="bundle-hash">sha256:{bundle.content_hash}</code>
        </div>
        <div className="bundle-actions">
          {canAuthor(roles) && !editing && bundle.state === "draft" && (
            <Link
              className="btn"
              href={`/bundles/${bundle.id}/edit?revision=${bundle.revision}&document=${encodeURIComponent(active.key)}`}
            >
              {t("edit")}
            </Link>
          )}
          {canAuthor(roles) && bundle.state === "draft" && (
            <button
              type="button"
              className="btn btn-solid"
              disabled={busy || !bundle.canSubmit}
              onClick={() => void transition("submit")}
            >
              {t("submit")}
            </button>
          )}
          {canAuthor(roles) && bundle.state === "submitted" && (
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => void transition("revisions")}
            >
              {t("newRevision")}
            </button>
          )}
        </div>
      </header>
      {notice && <p className="notice">{notice}</p>}
      {conflict && (
        <div className="catalog-state blocked">
          <div>
            <strong>{t("conflict")}</strong>
            <p>{t("conflictBody")}</p>
          </div>
          <button type="button" className="btn" onClick={() => void load()}>
            {t("rebase")}
          </button>
        </div>
      )}
      {!editing && (
        <section className="bundle-review" aria-label={t("reviewSummary")}>
          <div>
            <h2>{t("impact")}</h2>
            <ul>
              {operations.map((operation) => (
                <li key={textField(operation, "id", JSON.stringify(operation))}>
                  <strong>
                    {textField(operation, "operation", t("change"))}
                  </strong>{" "}
                  {textField(operation, "document_type", t("document"))} ·{" "}
                  {textField(operation, "id", t("document"))}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2>{t("sources")}</h2>
            {sources.length ? (
              <ul>
                {sources.map((source) => (
                  <li key={source}>{source}</li>
                ))}
              </ul>
            ) : (
              <p>{t("noSources")}</p>
            )}
          </div>
          <div>
            <h2>{t("gaps")}</h2>
            {gaps.length ? (
              <ul>
                {gaps.map((gap) => (
                  <li key={JSON.stringify(gap)}>
                    {textField(
                      gap,
                      "reason",
                      textField(gap, "capability", t("gapDeclared")),
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p>{t("noGaps")}</p>
            )}
          </div>
          <div>
            <h2>{t("compensation")}</h2>
            {gaps.length ? (
              <ul>
                {gaps.map((gap) => (
                  <li key={JSON.stringify(gap)}>
                    {textField(gap, "compensation", t("compensationMissing"))}
                  </li>
                ))}
              </ul>
            ) : (
              <p>{t("compensationNone")}</p>
            )}
          </div>
        </section>
      )}
      {!editing && bundle.state === "submitted" && canApprove(roles) && (
        <section
          className="bundle-decision"
          aria-labelledby="bundle-decision-title"
        >
          <div>
            <span>{t("humanDecision")}</span>
            <h2 id="bundle-decision-title">
              {t("decisionTitle", { revision: bundle.revision })}
            </h2>
            <p>{t("decisionBody")}</p>
          </div>
          <label>
            <span>{t("reason")}</span>
            <textarea
              value={reason}
              maxLength={1000}
              onChange={(event) => setReason(event.target.value)}
              placeholder={t("reasonPlaceholder")}
            />
          </label>
          <div className="bundle-decision-actions">
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy || !reason.trim()}
              onClick={() => void decide("reject")}
            >
              {t("reject")}
            </button>
            <button
              type="button"
              className="btn btn-solid"
              disabled={busy || !reason.trim()}
              onClick={() => void decide("approve")}
            >
              {t("approve")}
            </button>
          </div>
        </section>
      )}
      {currentDecision && (
        <section
          className={`bundle-decision-record ${currentDecision.decision}`}
        >
          <div>
            <span>{t("recordedDecision")}</span>
            <strong>{t(`decision.${currentDecision.decision}`)}</strong>
          </div>
          <p>{currentDecision.reason}</p>
          <dl>
            <div>
              <dt>{t("actor")}</dt>
              <dd>{currentDecision.approver_id}</dd>
            </div>
            <div>
              <dt>{t("correlation")}</dt>
              <dd>
                <code>{currentDecision.correlation_id}</code>
              </dd>
            </div>
          </dl>
        </section>
      )}
      {!editing && bundle.state === "approved" && canApprove(roles) && (
        <section
          className="bundle-publication"
          aria-labelledby="bundle-publication-title"
        >
          <header>
            <div>
              <span>{t("publicationEyebrow")}</span>
              <h2 id="bundle-publication-title">
                {t("publicationTitle", {
                  provider: t(`publicationProviders.${publicationProvider}`),
                })}
              </h2>
              <p>{t(`publicationBody.${publicationProvider}`)}</p>
            </div>
            <span className="catalog-status available">
              {t("publicationApproved")}
            </span>
          </header>
          {publication && ["pr_open", "merge_confirmed", "materializing", "completed", "compensating", "compensated", "compensation_required"].includes(publication.state) ? (
            <MaterializationPanel
              publication={publication}
              journal={publicationJournal}
              busy={busy}
              roles={roles}
              onAdvance={(action) =>
                void advanceMaterialization(publication, action)
              }
            />
          ) : (
            <>
              <div className="bundle-publication-fields">
                <label>
                  <span>{t("publicationProvider")}</span>
                  <select
                    value={publicationProvider}
                    onChange={(event) =>
                      setPublicationProvider(
                        event.target.value as "github" | "azure_devops",
                      )
                    }
                  >
                    <option value="github">
                      {t("publicationProviders.github")}
                    </option>
                    <option value="azure_devops">
                      {t("publicationProviders.azure_devops")}
                    </option>
                  </select>
                </label>
                <label>
                  <span>{t(`publicationOwner.${publicationProvider}`)}</span>
                  <input
                    value={publicationOwner}
                    maxLength={100}
                    autoComplete="off"
                    onChange={(event) =>
                      setPublicationOwner(event.target.value)
                    }
                    placeholder={t("publicationOwnerPlaceholder")}
                  />
                </label>
                {publicationProvider === "azure_devops" && (
                  <label>
                    <span>{t("publicationProject")}</span>
                    <input
                      value={publicationProject}
                      maxLength={128}
                      autoComplete="off"
                      onChange={(event) =>
                        setPublicationProject(event.target.value)
                      }
                      placeholder={t("publicationProjectPlaceholder")}
                    />
                  </label>
                )}
                <label>
                  <span>{t("publicationRepository")}</span>
                  <input
                    value={publicationRepository}
                    maxLength={100}
                    autoComplete="off"
                    onChange={(event) =>
                      setPublicationRepository(event.target.value)
                    }
                    placeholder={t("publicationRepositoryPlaceholder")}
                  />
                </label>
                <label>
                  <span>{t("publicationBase")}</span>
                  <input
                    value={publicationBranch}
                    maxLength={128}
                    autoComplete="off"
                    onChange={(event) =>
                      setPublicationBranch(event.target.value)
                    }
                  />
                </label>
                <label>
                  <span>{t("publicationDirectory")}</span>
                  <input
                    value={publicationDirectory}
                    maxLength={128}
                    autoComplete="off"
                    onChange={(event) =>
                      setPublicationDirectory(event.target.value)
                    }
                  />
                </label>
              </div>
              <footer>
                <p>{t(`publicationConsent.${publicationProvider}`)}</p>
                <button
                  type="button"
                  className="btn btn-solid"
                  disabled={
                    busy ||
                    toolApproval !== null ||
                    !publicationFieldsReady(
                      publicationProvider,
                      publicationOwner,
                      publicationProject,
                      publicationRepository,
                    ) ||
                    !publicationBranch.trim() ||
                    !publicationDirectory.trim()
                  }
                  onClick={() => void publish()}
                >
                  {busy ? t("publicationPublishing") : t("publicationAction")}
                </button>
              </footer>
            </>
          )}
          <ToolApprovalPanel
            approval={toolApproval}
            busy={busy}
            onDecision={(approved) => void decidePublicationTool(approved)}
          />
          {consentUrl && (
            <a
              className="bundle-consent-link"
              href={consentUrl}
              target="_blank"
              rel="noreferrer"
            >
              {t("publicationOpenConsent")}
            </a>
          )}
          {publicationStatus && (
            <output className="bundle-publication-status">
              {publicationStatus}
            </output>
          )}
        </section>
      )}
      <div className="bundle-workspace">
        <aside className="bundle-tree" aria-label={t("tree")}>
          <strong>{t("documents")}</strong>
          {bundle.documents.map((document) => (
            <button
              type="button"
              className={document.key === active.key ? "selected" : ""}
              key={document.key}
              onClick={() => selectDocument(document)}
            >
              <span>{document.type}</span>
              <b>{document.id}</b>
              <small>@{document.revision}</small>
            </button>
          ))}
        </aside>
        <main className="bundle-document">
          <header>
            <div>
              <span>{active.type}</span>
              <h2>{active.id}</h2>
            </div>
            <code>{active.key}</code>
          </header>
          {editing ? (
            <textarea
              aria-label={t("documentSource")}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              spellCheck={false}
            />
          ) : (
            <pre>{active.text}</pre>
          )}
          {editing && (
            <footer>
              <button
                type="button"
                className="btn btn-solid"
                disabled={busy || draft === active.text}
                onClick={() => void save()}
              >
                {t("save")}
              </button>
            </footer>
          )}
        </main>
        <aside className="bundle-inspector">
          <section>
            <h3>{t("validations")}</h3>
            {bundle.validations.map((check) => (
              <div className={`bundle-check ${check.status}`} key={check.id}>
                <strong>{check.id}</strong>
                <p>{check.reason}</p>
              </div>
            ))}
          </section>
          <section>
            <h3>{t("dependencies")}</h3>
            {bundle.dependencies.length === 0 ? (
              <p className="muted">{t("none")}</p>
            ) : (
              bundle.dependencies
                .filter((dependency) => dependency.from === active.key)
                .map((dependency) => (
                  <div
                    className="bundle-dependency"
                    key={`${dependency.from}-${dependency.to}`}
                  >
                    <code>{dependency.to}</code>
                    <span>{dependency.source}</span>
                  </div>
                ))
            )}
          </section>
          <section>
            <h3>{t("diff")}</h3>
            {diff.truncated ? (
              <p>{t("diffLarge")}</p>
            ) : (
              <div className="bundle-diff">
                {diff.parts.map((part, index) => (
                  <span className={part.op} key={`${part.op}-${index}`}>
                    {part.text}
                  </span>
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
