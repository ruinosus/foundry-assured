"use client";

// Skills — o terceiro recurso da spec, e o que tem a armadilha mais sutil.
//
// Skill é versionada como o agente, mas com uma diferença que a interface PRECISA mostrar:
// `default_version` e `latest_version` são campos separados no serviço. Publicar uma versão nova
// não troca o que está em uso se a default não acompanhar. O sintoma é "publiquei e nada mudou",
// e sem os dois campos lado a lado ninguém descobre por quê.
//
// O formato é agentskills.io — padrão aberto, não nosso. O campo aceita o documento como ele é.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { useMyRoles, canAdmin } from "@/lib/auth/roles";
import { SkillCatalog } from "@/components/skills/SkillCatalog";
import { SkillWizard } from "@/components/skills/SkillWizard";

type Version = { version: string | null; description: string | null; created_at: string | null };

type Skill = {
  name: string;
  id: string | null;
  description: string | null;
  default: Version | null;
  latest: Version | null;
  latest_is_default: boolean;
};

export function SkillsView() {
  const t = useTranslations("skills");
  const tc = useTranslations("common");
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [importOpen, setImport_] = useState(false);
  const roles = useMyRoles();
  const admin = canAdmin(roles);

  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authedFetch("/api/foundry/skills", { cache: "no-store" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setSkills(null);
        setError(body?.error ?? `${t("errorTitle")} (HTTP ${r.status}).`);
      } else {
        setSkills(body.skills ?? []);
      }
    } catch {
      setSkills(null);
      setError(tc("backendUnreachable"));
    } finally {
      setLoading(false);
    }
  }, [t, tc]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="stack">
      <header className="between">
        <div>
          <h2 className="page-title">{t("title")}</h2>
          <p className="page-sub">{t("subtitle")}</p>
        </div>
        <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
          {loading ? tc("refreshing") : tc("refresh")}
        </button>
      </header>

      {notice && (
        <div className="notice">
          <p className="notice-body">{notice}</p>
        </div>
      )}

      {admin &&
        (open ? (
          <SkillWizard
            existentes={(skills ?? []).map((s) => s.name)}
            onCancelar={() => setOpen(false)}
            onConcluido={() => {
              setOpen(false);
              setNotice(t("published"));
              void load();
            }}
          />
        ) : (
          <div className="row-tight">
            <button type="button" className="btn btn-solid" onClick={() => setOpen(true)}>
              {t("newBtn")}
            </button>
            {/* Importar vem ao lado de criar, não escondido: para a maioria dos casos a skill
                que a pessoa quer JÁ EXISTE num catálogo público, e escrever do zero é a opção
                mais cara das duas. */}
            <button type="button" className="btn" onClick={() => setImport_(v => !v)}>
              {importOpen ? tc("cancel") : t("importBtn")}
            </button>
          </div>
        ))}

      {admin && importOpen && !open && (
        <SkillCatalog
          onImported={() => {
            void load();
          }}
        />
      )}

      {loading && skills === null && !error && (
        <div className="skeleton-list" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton-row" />
          ))}
        </div>
      )}

      {error && (
        <div className="notice notice-block">
          <p className="notice-title">{t("errorTitle")}</p>
          <p className="notice-body">{error}</p>
          <button type="button" className="btn" onClick={() => void load()}>
            {tc("retry")}
          </button>
        </div>
      )}

      {!error && skills !== null && skills.length === 0 && (
        <div className="empty">
          <p className="empty-title">{t("emptyTitle")}</p>
          <p className="empty-body">{t("emptyBody")}</p>
        </div>
      )}

      {!error && skills !== null && skills.length > 0 && (
        <div className="grid">
          {skills.map((s) => (
            <article key={s.name} className="card skill-card">
              <header className="between">
                <h3 className="skill-name">{s.name}</h3>
                {/* Os dois lado a lado, sempre: é o que explica "publiquei e nada mudou". */}
                <span className={`pill ${s.latest_is_default ? "ok" : "wait"}`}>
                  {s.latest_is_default ? t("inUsePill") : t("notDefaultPill")}
                </span>
              </header>
              {s.description && <p className="t-sm muted-line">{s.description}</p>}
              <dl className="skill-versions">
                <div>
                  <dt>{t("colDefault")}</dt>
                  <dd className="t-mono">{s.default?.version ?? "—"}</dd>
                </div>
                <div>
                  <dt>{t("colLatest")}</dt>
                  <dd className="t-mono">{s.latest?.version ?? "—"}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
