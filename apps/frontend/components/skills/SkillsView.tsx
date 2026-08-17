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

type Version = { version: string | null; description: string | null; created_at: string | null };

type Skill = {
  name: string;
  id: string | null;
  description: string | null;
  default: Version | null;
  latest: Version | null;
  latest_is_default: boolean;
};

/** O exemplo do campo: estrutura aqui, frase do dicionário — `{}` no dicionário quebra o ICU. */
function exampleSkill(instructions: string): string {
  return JSON.stringify({ instructions, license: "MIT" }, null, 2);
}

export function SkillsView() {
  const t = useTranslations("skills");
  const tc = useTranslations("common");
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const roles = useMyRoles();
  const admin = canAdmin(roles);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [doc, setDoc] = useState("");
  const [busy, setBusy] = useState(false);
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

  const publish = async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(doc);
    } catch {
      setNotice(t("invalidJson"));
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const r = await authedFetch("/api/foundry/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, content: parsed, default: true }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setNotice(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      const ignored = (body?.ignored_fields ?? []) as string[];
      setNotice(
        ignored.length
          ? `${t("published")} ${t("ignoredFields", { fields: ignored.join(", ") })}`
          : t("published"),
      );
      setOpen(false);
      setDoc("");
      setName("");
      void load();
    } catch {
      setNotice(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

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
          <section className="card stack-sm">
            <h3 className="section-title">{t("createTitle")}</h3>
            <p className="muted t-sm">{t("createHelp")}</p>
            <input
              className="acct-btn"
              placeholder={t("namePlaceholder")}
              value={name}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
            />
            <textarea
              className="acct-btn"
              rows={8}
              spellCheck={false}
              placeholder={exampleSkill(t("exampleInstructions"))}
              value={doc}
              disabled={busy}
              onChange={(e) => setDoc(e.target.value)}
            />
            <div className="row">
              <button
                type="button"
                className="btn btn-solid"
                disabled={busy || !name.trim() || !doc.trim()}
                onClick={() => void publish()}
              >
                {t("createBtn")}
              </button>
              <button type="button" className="btn" disabled={busy} onClick={() => setOpen(false)}>
                {tc("cancel")}
              </button>
            </div>
          </section>
        ) : (
          <button type="button" className="btn btn-solid" onClick={() => setOpen(true)}>
            {t("newBtn")}
          </button>
        ))}

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
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("colName")}</th>
                <th>{t("colDefault")}</th>
                <th>{t("colLatest")}</th>
                <th>{t("colSync")}</th>
              </tr>
            </thead>
            <tbody>
              {skills.map((s) => (
                <tr key={s.name}>
                  <td>
                    <span className="strong">{s.name}</span>
                    {s.description && <p className="t-xs muted-line">{s.description}</p>}
                  </td>
                  {/* Os dois lado a lado, sempre. É o que explica "publiquei e nada mudou". */}
                  <td className="t-mono t-sm">{s.default?.version ?? "—"}</td>
                  <td className="t-mono t-sm">{s.latest?.version ?? "—"}</td>
                  <td>
                    <span className={`pill ${s.latest_is_default ? "ok" : "wait"}`}>
                      {s.latest_is_default ? t("inUsePill") : t("notDefaultPill")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
