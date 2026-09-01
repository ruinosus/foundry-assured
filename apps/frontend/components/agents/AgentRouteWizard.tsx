"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { FormFlowFields, FormFlowProposalTool, useFormFlow } from "@/components/formflow/FormFlow";
import { AREA_SELECTION_EVENT, selectedAreaId } from "@/lib/area-selection";
import { authedFetch } from "@/lib/auth/api";
import { useMyIdentity } from "@/lib/auth/roles";
import { useManifest } from "@/lib/formflow/load";
import type { FormFlowManifest, Valores } from "@/lib/formflow/types";

type Route = "prompt" | "workflow" | "container";
type StoredDraft = {
  id: string;
  revision: number;
  etag: string;
  content: { form_values?: Valores };
};

const REFERENCE_FIELD: Record<Route, string> = {
  prompt: "prompt_definition",
  workflow: "workflow_definition",
  container: "container_image",
};

function errorCode(body: unknown): string {
  if (!body || typeof body !== "object") return "UNKNOWN";
  const value = body as { detail?: unknown; error?: { code?: unknown } };
  return String(value.error?.code ?? value.detail ?? "UNKNOWN");
}

function RouteForm({ manifest, onCancel }: { manifest: FormFlowManifest; onCancel: () => void }) {
  const t = useTranslations("authoringRoutes");
  const tf = useTranslations("formflow");
  const identity = useMyIdentity();
  const [selectedArea, setSelectedArea] = useState<string | null>(() => selectedAreaId());
  const [lookupId, setLookupId] = useState("");
  const [record, setRecord] = useState<StoredDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const { estado, set, setValores, regraDoCampo, aplicarProposta, catalogos } = useFormFlow(manifest);

  const areaId = identity?.areas.some((area) => area.id === selectedArea)
    ? selectedArea
    : (identity?.areas[0]?.id ?? null);

  useEffect(() => {
    const onArea = (event: Event) => {
      setSelectedArea((event as CustomEvent<string | null>).detail);
      setRecord(null);
    };
    window.addEventListener(AREA_SELECTION_EVENT, onArea);
    return () => window.removeEventListener(AREA_SELECTION_EVENT, onArea);
  }, []);

  const text = (id: string) => String(estado.valores[id] ?? "").trim();
  const route = (text("authoring_route") || "prompt") as Route;
  const reference = text(REFERENCE_FIELD[route]);

  const documentText = () => {
    const name = text("name");
    const header = {
      type: "agent-binding",
      resource: `${route}:${reference}`,
      status: "draft",
      generated: {
        by: `human:${identity?.oid ?? "local-author"}`,
        at: new Date().toISOString(),
      },
      "x-foundry-authoring": {
        profile_version: "1",
        id: name,
        revision: "1",
        publication_state: "proposed",
        tenant: identity?.tenant_id ?? "self-hosted",
        area: areaId,
        spec: {
          agent: { name, version: text("version") },
          authoringRoute: route,
        },
      },
    };
    return `---\n${JSON.stringify(header, null, 2)}\n---\n\n# ${name}\n\n${text("justification")}\n`;
  };

  const content = () => ({
    justification: text("justification"),
    form_values: estado.valores,
    operations: [{
      id: `create-${text("name")}`,
      operation: "create",
      document_type: "agent-binding",
      document: documentText(),
    }],
  });

  const load = async () => {
    if (!areaId || !lookupId.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await authedFetch(`/api/authoring/changesets/${encodeURIComponent(lookupId.trim())}`, {
        cache: "no-store",
        headers: { "X-Area-ID": areaId },
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorCode(body));
      const draft = body as StoredDraft;
      if (!draft.content?.form_values || typeof draft.content.form_values !== "object") {
        throw new Error("INCOMPATIBLE_CHANGESET");
      }
      setValores(draft.content.form_values);
      setRecord(draft);
      setLookupId(draft.id);
      setNotice(t("loaded", { revision: draft.revision }));
    } catch (caught) {
      setNotice(t("failed", { code: caught instanceof Error ? caught.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!areaId || !identity || estado.bloqueio) return;
    setBusy(true);
    setNotice(null);
    try {
      let response: Response;
      if (record) {
        response = await authedFetch(`/api/authoring/changesets/${encodeURIComponent(record.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", "If-Match": record.etag, "X-Area-ID": areaId },
          body: JSON.stringify({ content: content() }),
        });
      } else {
        const catalog = await authedFetch("/api/authoring/catalog?limit=1", {
          cache: "no-store",
          headers: { "X-Area-ID": areaId },
        });
        const catalogBody = await catalog.json().catch(() => ({}));
        if (!catalog.ok || !catalogBody.snapshot?.id) throw new Error(errorCode(catalogBody));
        response = await authedFetch("/api/authoring/changesets", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
            "X-Area-ID": areaId,
          },
          body: JSON.stringify({ source: "manual", base_snapshot_id: catalogBody.snapshot.id, content: content() }),
        });
      }
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(errorCode(body));
      const saved = body as StoredDraft;
      setRecord(saved);
      setLookupId(saved.id);
      setNotice(t("saved", { revision: saved.revision }));
    } catch (caught) {
      setNotice(t("failed", { code: caught instanceof Error ? caught.message : "UNKNOWN" }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card wizard authoring-route-wizard">
      <FormFlowProposalTool manifest={manifest} valores={estado.valores} regraDoCampo={regraDoCampo} onAccept={aplicarProposta} />
      <header className="between wizard-head">
        <div><h3 className="section-title">{t("title")}</h3><p className="muted t-sm">{t("subtitle")}</p></div>
        <div className="row-tight"><button type="button" className="btn" onClick={onCancel}>{t("cancel")}</button><button type="button" className="btn btn-solid" disabled={busy || !!estado.bloqueio || !areaId} onClick={() => void save()}>{busy ? t("saving") : record ? t("saveRevision") : t("saveDraft")}</button></div>
      </header>

      <div className="authoring-route-resume">
        <label><span className="t-xs strong">{t("changesetId")}</span><input className="acct-btn" value={lookupId} onChange={(event) => setLookupId(event.target.value)} placeholder={t("changesetPlaceholder")} /></label>
        <button type="button" className="btn" disabled={busy || !areaId || !lookupId.trim()} onClick={() => void load()}>{t("load")}</button>
      </div>
      {notice && <p className="notice notice-body" role="status">{notice}</p>}
      {estado.bloqueio && <p className="t-xs muted-line">{estado.bloqueio}</p>}

      <div className="wizard-form">
        <FormFlowFields manifest={manifest} valores={estado.valores} set={set} regraDoCampo={regraDoCampo} catalogos={catalogos} busy={busy} origens={estado.origens} />
        <section className="wizard-section">
          <h4 className="wizard-section-title">{tf("step4")}</h4>
          <dl className="review">{estado.revisao.map((line) => <div key={line.label}><dt>{line.label}</dt><dd>{line.texto}</dd></div>)}</dl>
          <details className="wizard-doc"><summary className="t-xs">{t("technicalDefinition")}</summary><pre className="doc-preview">{areaId ? documentText() : t("selectArea")}</pre></details>
          <p className="t-xs muted-line">{t(`routeNotes.${route}`)}</p>
        </section>
      </div>
    </section>
  );
}

export function AgentRouteWizard({ onCancel }: { onCancel: () => void }) {
  const t = useTranslations("authoringRoutes");
  const flow = useManifest("agent-route");
  if (flow.estado === "ok") return <RouteForm manifest={flow.manifest} onCancel={onCancel} />;
  return <section className="card"><p className="muted t-sm">{flow.estado === "carregando" ? t("loading") : t("manifestError")}</p></section>;
}