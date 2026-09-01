"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { AREA_SELECTION_EVENT } from "@/lib/area-selection";
import { authedFetch } from "@/lib/auth/api";
import { canApprove, canAuthor, useMyRoles } from "@/lib/auth/roles";

type Phase = "editing" | "submission" | "approval" | "materialization";
type Status = "approved" | "failed" | "pending";

interface BundleSummary {
  id: string;
  revision: number;
  bundle: { id: string };
}

interface ValidationCheck {
  id: string;
  status: Status;
  blocking: boolean;
  source: string;
  severity: "error" | "warning" | "info";
  reason: string;
  evidence: Record<string, unknown>;
}

interface ValidationReport {
  id: string;
  revision: number;
  phase: Phase;
  overall: Status;
  content_hash: string;
  checks: ValidationCheck[];
  blocks_transition: boolean;
  created_at: string;
}

async function request(path: string, init?: RequestInit) {
  const response = await authedFetch(`/api/authoring/${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error?.code || body.detail || `HTTP_${response.status}`);
  return body;
}

const PHASES: Phase[] = ["editing", "submission", "approval", "materialization"];

export function ComplianceWorkspace() {
  const t = useTranslations("compliance");
  const roles = useMyRoles();
  const [bundles, setBundles] = useState<BundleSummary[]>([]);
  const [bundleId, setBundleId] = useState("");
  const [revision, setRevision] = useState(1);
  const [phase, setPhase] = useState<Phase>("submission");
  const [reports, setReports] = useState<ValidationReport[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const loadReports = useCallback(async (id: string, nextRevision: number, nextPhase: Phase) => {
    if (!id) return setReports([]);
    const result = await request(`changesets/${encodeURIComponent(id)}/validations?revision=${nextRevision}&phase=${nextPhase}`);
    const items = (result.items ?? []) as ValidationReport[];
    setReports(items);
    setSelectedId((current) => items.some((item) => item.id === current) ? current : (items[0]?.id ?? ""));
  }, []);

  const load = useCallback(async () => {
    setNotice(null);
    try {
      const result = await request("bundles");
      const items = (result.items ?? []) as BundleSummary[];
      setBundles(items);
      const chosen = items.find((item) => item.id === bundleId) ?? items[0];
      if (!chosen) {
        setBundleId("");
        setReports([]);
        return;
      }
      setBundleId(chosen.id);
      setRevision(chosen.revision);
      await loadReports(chosen.id, chosen.revision, phase);
    } catch (error) {
      setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    }
  }, [bundleId, loadReports, phase, t]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => { if (active) void load(); });
    const onArea = () => void load();
    window.addEventListener(AREA_SELECTION_EVENT, onArea);
    return () => {
      active = false;
      window.removeEventListener(AREA_SELECTION_EVENT, onArea);
    };
  }, [load]);

  const chooseBundle = async (id: string) => {
    setBundleId(id);
    const chosen = bundles.find((item) => item.id === id);
    if (!chosen) return;
    setRevision(chosen.revision);
    setNotice(null);
    try { await loadReports(id, chosen.revision, phase); }
    catch (error) { setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" })); }
  };

  const choosePhase = async (nextPhase: Phase) => {
    setPhase(nextPhase);
    setNotice(null);
    try { await loadReports(bundleId, revision, nextPhase); }
    catch (error) { setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" })); }
  };

  const run = async () => {
    if (!bundleId) return;
    setBusy(true);
    setNotice(null);
    try {
      const report = await request(`changesets/${encodeURIComponent(bundleId)}/validations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revision, phase }),
      }) as ValidationReport;
      setReports((current) => [report, ...current]);
      setSelectedId(report.id);
    } catch (error) {
      setNotice(t("failed", { code: error instanceof Error ? error.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const report = reports.find((item) => item.id === selectedId) ?? reports[0];
  const mayRun = phase === "approval" || phase === "materialization"
    ? canApprove(roles)
    : canAuthor(roles);
  const covered = report?.checks.filter((check) => check.status !== "pending").length ?? 0;
  let content = <div className="catalog-state"><div><strong>{t("empty")}</strong><p>{t("emptyBody")}</p></div></div>;
  if (bundleId && !report) content = <div className="catalog-state"><div><strong>{t("noReportTitle")}</strong><p>{t("noReportBody")}</p></div></div>;
  if (bundleId && report) content = <>
    <section className={`compliance-summary ${report.overall}`} aria-label={t("summary")}>
      <div><span>{t("result")}</span><strong>{t(`status.${report.overall}`)}</strong></div>
      <div><span>{t("transition")}</span><strong>{report.blocks_transition ? t("blocked") : t("released")}</strong></div>
      <div><span>{t("coverage")}</span><strong>{t("coverageValue", { covered, total: report.checks.length })}</strong></div>
      <div><span>{t("report")}</span><code>{report.id}</code></div>
    </section>
    <section className="compliance-checks" aria-label={t("checks")}>
      {report.checks.map((check) => <article className={`compliance-check ${check.status}`} key={check.id}>
        <header><div><h2>{check.id}</h2><p>{check.reason}</p></div><span className={`compliance-state ${check.status}`}>{t(`status.${check.status}`)}</span></header>
        <dl className="compliance-facts"><div><dt>{t("source")}</dt><dd>{check.source}</dd></div><div><dt>{t("severity")}</dt><dd>{t(`severityValue.${check.severity}`)}</dd></div><div><dt>{t("effect")}</dt><dd>{check.blocking ? t("blocking") : t("informative")}</dd></div></dl>
        <details><summary>{t("evidence")}</summary><pre>{JSON.stringify(check.evidence, null, 2)}</pre></details>
      </article>)}
    </section>
  </>;

  return <div className="compliance-page">
    <header className="compliance-heading">
      <div><h1>{t("title")}</h1><p>{t("subtitle")}</p></div>
      <button className="btn btn-solid" type="button" disabled={!bundleId || busy || !mayRun} onClick={() => void run()}>{busy ? t("running") : t("run")}</button>
    </header>

    <section className="compliance-controls" aria-label={t("filters")}>
      <label><span>{t("bundle")}</span><select value={bundleId} onChange={(event) => void chooseBundle(event.target.value)}><option value="">{t("chooseBundle")}</option>{bundles.map((item) => <option key={item.id} value={item.id}>{item.bundle.id} · {t("revision", { revision: item.revision })}</option>)}</select></label>
      <label><span>{t("revisionLabel")}</span><input type="number" min="1" value={revision} readOnly /></label>
      <label><span>{t("phaseLabel")}</span><select value={phase} onChange={(event) => void choosePhase(event.target.value as Phase)}>{PHASES.map((item) => <option key={item} value={item}>{t(`phase.${item}`)}</option>)}</select></label>
      <label><span>{t("history")}</span><select value={selectedId} disabled={!reports.length} onChange={(event) => setSelectedId(event.target.value)}><option value="">{t("noReports")}</option>{reports.map((item) => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {t(`status.${item.overall}`)}</option>)}</select></label>
    </section>

    {notice && <output className="notice">{notice}</output>}
    {content}
  </div>;
}
