"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { AREA_SELECTION_EVENT, selectedAreaId } from "@/lib/area-selection";
import { authedFetch } from "@/lib/auth/api";
import { useMyIdentity } from "@/lib/auth/roles";
import { ChangeSetTracer } from "./ChangeSetTracer";

type CatalogItem = {
  kind: string;
  id: string;
  name: string;
  state: string;
  source: string;
  selectable: boolean;
};

type Gap = { kind: string; source: string; code: string };
type Snapshot = { id: string; hash: string; at: string };
type Collection = {
  items: Record<string, unknown>[];
  next_cursor: string | null;
  source: string;
  state: "measured" | "unavailable";
  coverage: string;
};
type Detail = {
  kind: string;
  id: string;
  source: string;
  definition: Record<string, unknown>;
  lifecycle: Fact;
  cost: Fact;
  permissions: Fact & { value: Record<string, boolean>; area_id: string | null };
};
type Fact = {
  state: "measured" | "estimated" | "unavailable" | "pending";
  value: unknown;
  source: string;
  observed_at: string;
  reason?: string;
};

const KINDS = ["agent", "knowledge", "skill", "toolbox", "connection", "usecase", "formflow", "copilot"];
const STATES = ["active", "available", "compatible", "configuration_required", "shadow", "quarantined", "unavailable"];

function errorCode(body: unknown): string {
  if (!body || typeof body !== "object") return "UNKNOWN";
  const error = (body as { error?: unknown }).error;
  if (typeof error === "object" && error) return String((error as { code?: unknown }).code ?? "UNKNOWN");
  return "UNKNOWN";
}

export function CatalogView() {
  const t = useTranslations("catalog");
  const common = useTranslations("common");
  const identity = useMyIdentity();
  const [areaId, setAreaId] = useState<string | null>(() => selectedAreaId());
  const [kind, setKind] = useState("");
  const [state, setState] = useState("");
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [stale, setStale] = useState(false);
  const [selected, setSelected] = useState<CatalogItem | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [versions, setVersions] = useState<Collection | null>(null);
  const [activity, setActivity] = useState<Collection | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const effectiveArea = identity?.areas.some((area) => area.id === areaId)
    ? areaId
    : (identity?.areas[0]?.id ?? null);

  useEffect(() => {
    const onArea = (event: Event) => {
      setAreaId((event as CustomEvent<string | null>).detail);
      setSelected(null);
    };
    window.addEventListener(AREA_SELECTION_EVENT, onArea);
    return () => window.removeEventListener(AREA_SELECTION_EVENT, onArea);
  }, []);

  const load = useCallback(async (cursor?: string) => {
    if (identity === null) return;
    if (!effectiveArea) {
      setLoading(false);
      setItems([]);
      return;
    }

    cursor ? setLoadingMore(true) : setLoading(true);
    if (!cursor) {
      setError(null);
      setForbidden(false);
      setStale(false);
    }
    const query = new URLSearchParams({ limit: "50" });
    if (kind) query.set("kind", kind);
    if (state) query.set("state", state);
    if (cursor) query.set("cursor", cursor);

    try {
      const response = await authedFetch(`/api/authoring/catalog?${query}`, {
        cache: "no-store",
        headers: { "X-Area-ID": effectiveArea },
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const code = errorCode(body);
        if (response.status === 403) setForbidden(true);
        else if (response.status === 409 && code === "SNAPSHOT_STALE") setStale(true);
        else setError(code);
        return;
      }
      const incoming = Array.isArray(body.items) ? body.items : [];
      setItems((current) => cursor ? [...current, ...incoming] : incoming);
      setGaps(Array.isArray(body.gaps) ? body.gaps : []);
      setSnapshot(body.snapshot ?? null);
      setNextCursor(body.next_cursor ?? null);
    } catch {
      setError("BACKEND_UNAVAILABLE");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [effectiveArea, identity, kind, state]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  useEffect(() => {
    if (!selected || !effectiveArea) return;
    const controller = new AbortController();
    const base = `/api/authoring/resources/${encodeURIComponent(selected.kind)}/${encodeURIComponent(selected.id)}`;
    const options = { cache: "no-store" as const, headers: { "X-Area-ID": effectiveArea }, signal: controller.signal };
    Promise.all([authedFetch(base, options), authedFetch(`${base}/versions`, options), authedFetch(`${base}/activity`, options)])
      .then(async ([detailResponse, versionResponse, activityResponse]) => {
        const [detailBody, versionBody, activityBody] = await Promise.all([
          detailResponse.json().catch(() => ({})),
          versionResponse.json().catch(() => ({})),
          activityResponse.json().catch(() => ({})),
        ]);
        if (!detailResponse.ok) throw new Error(errorCode(detailBody));
        setDetail(detailBody);
        setVersions(versionResponse.ok ? versionBody : null);
        setActivity(activityResponse.ok ? activityBody : null);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setDetailError(caught instanceof Error ? caught.message : "UNKNOWN");
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });
    return () => controller.abort();
  }, [effectiveArea, selected]);

  const noArea = identity !== null && !effectiveArea;
  const openDetail = (item: CatalogItem) => {
    setDetail(null);
    setVersions(null);
    setActivity(null);
    setDetailError(null);
    setDetailLoading(true);
    setSelected(item);
  };

  return (
    <section className="catalog-page">
      <header className="catalog-heading">
        <div>
          <h2 className="page-title">{t("title")}</h2>
          <p className="page-sub">{t("subtitle")}</p>
        </div>
        {snapshot && <span className="catalog-snapshot" title={snapshot.hash}>{t("observedAt", { at: new Date(snapshot.at).toLocaleString() })}</span>}
      </header>

      <div className="catalog-filters" aria-label={t("filters")}>
        <label>
          <span>{t("kind")}</span>
          <select value={kind} onChange={(event) => { setSelected(null); setKind(event.target.value); }}>
            <option value="">{t("allKinds")}</option>
            {KINDS.map((value) => <option key={value} value={value}>{t(`kinds.${value}`)}</option>)}
          </select>
        </label>
        <label>
          <span>{t("state")}</span>
          <select value={state} onChange={(event) => { setSelected(null); setState(event.target.value); }}>
            <option value="">{t("allStates")}</option>
            {STATES.map((value) => <option key={value} value={value}>{t(`states.${value}`)}</option>)}
          </select>
        </label>
        <button type="button" className="btn" onClick={() => void load()} disabled={loading}>{common("refresh")}</button>
      </div>

      {stale && <div className="catalog-state wait"><div><strong>{t("staleTitle")}</strong><p>{t("staleBody")}</p></div><button className="btn" type="button" onClick={() => void load()}>{t("reload")}</button></div>}
      {gaps.length > 0 && <div className="catalog-state partial"><div><strong>{t("partialTitle")}</strong><p>{t("partialBody")}</p><ul>{gaps.map((gap) => <li key={`${gap.kind}-${gap.source}`}>{gap.source} · {t(`kinds.${gap.kind}`)}</li>)}</ul></div></div>}
      {forbidden && <div className="catalog-state blocked"><div><strong>{t("forbiddenTitle")}</strong><p>{t("forbiddenBody")}</p></div></div>}
      {noArea && <div className="catalog-state blocked"><div><strong>{t("noAreaTitle")}</strong><p>{t("noAreaBody")}</p></div></div>}
      {error && <div className="catalog-state blocked"><div><strong>{t("errorTitle")}</strong><p>{t("errorBody", { code: error })}</p></div><button className="btn" type="button" onClick={() => void load()}>{common("retry")}</button></div>}

      <div className={`catalog-layout${selected ? " has-detail" : ""}`}>
        <div className="catalog-results">
          {loading && items.length === 0 && <div className="catalog-skeleton" aria-label={common("loading")}><span /><span /><span /><span /></div>}
          {!loading && !error && !forbidden && !noArea && !stale && items.length === 0 && <div className="empty"><p className="empty-title">{t("emptyTitle")}</p><p className="empty-body">{t("emptyBody")}</p></div>}
          {items.length > 0 && <div className="table-wrap"><table className="tbl catalog-table"><thead><tr><th>{t("resource")}</th><th>{t("kind")}</th><th>{t("state")}</th><th>{t("source")}</th></tr></thead><tbody>{items.map((item) => <tr key={`${item.kind}:${item.id}`} className={selected?.kind === item.kind && selected.id === item.id ? "selected" : ""}><td><button type="button" className="catalog-resource" onClick={() => openDetail(item)}><strong>{item.name}</strong><small>{item.id}</small></button></td><td>{t(`kinds.${item.kind}`)}</td><td><span className={`catalog-status ${item.selectable ? "available" : "unavailable"}`}>{t(`states.${item.state}`)}</span></td><td>{item.source}</td></tr>)}</tbody></table></div>}
          {nextCursor && <button type="button" className="btn catalog-more" disabled={loadingMore} onClick={() => void load(nextCursor)}>{loadingMore ? common("loading") : t("loadMore")}</button>}
        </div>

        {selected && <aside className="catalog-detail" aria-label={t("detailTitle")}><header><div><span>{t(`kinds.${selected.kind}`)}</span><h3>{selected.name}</h3><code>{selected.id}</code></div><button type="button" className="btn" onClick={() => setSelected(null)}>{t("close")}</button></header>{detailLoading && <div className="catalog-detail-loading"><span /><span /><span /></div>}{detailError && <div className="catalog-detail-error"><strong>{t("detailError")}</strong><p>{detailError}</p></div>}{detail && !detailLoading && <div className="catalog-detail-body"><section><h4>{t("facts")}</h4><dl className="catalog-facts"><div><dt>{t("lifecycle")}</dt><dd>{String(detail.lifecycle.value)}</dd><small>{detail.lifecycle.source}</small></div><div><dt>{t("cost")}</dt><dd>{t(`factStates.${detail.cost.state}`)}</dd><small>{t("costUnavailable")}</small></div></dl></section><section><h4>{t("permissions")}</h4><div className="catalog-permissions">{Object.entries(detail.permissions.value).map(([permission, allowed]) => <span key={permission} className={allowed ? "allowed" : "denied"}>{t(`permissionNames.${permission}`)} · {allowed ? t("allowed") : t("denied")}</span>)}</div><small>{detail.permissions.source}</small></section><section><h4>{t("versions")}</h4><p>{versions?.state === "measured" ? t("versionCount", { count: versions.items.length }) : t("unavailable")}</p><small>{versions?.source ?? detail.source}</small></section><section><h4>{t("activity")}</h4><p>{activity?.state === "measured" ? t("activityCount", { count: activity.items.length }) : t("unavailable")}</p><small>{activity ? t(`coverage.${activity.coverage}`) : detail.source}</small></section><details><summary>{t("definition")}</summary><pre>{JSON.stringify(detail.definition, null, 2)}</pre></details></div>}</aside>}
      </div>
      <ChangeSetTracer areaId={effectiveArea} snapshotId={snapshot?.id ?? null} />
    </section>
  );
}