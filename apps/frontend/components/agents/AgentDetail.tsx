"use client";

// Detalhe de um agente — versões, sessões e as ações que mudam o recurso.
//
// A tela existe para responder três perguntas que a lista não responde: o que mudou e quando,
// com qual versão cada conversa rodou, e como publicar a próxima. As três vêm do fato de o
// agente ser recurso VERSIONADO — e é por isso que o botão diz "Publicar versão", não "Salvar".
// Um "Salvar" prometeria edição in-place, que não é o que o serviço faz: cada publicação cria
// uma versão nova e a anterior continua existindo.
//
// Duas ações destrutivas, tratadas de forma diferente por serem diferentes:
//   * DESABILITAR é reversível — o agente para de atender, versões e sessões ficam. Um clique.
//   * APAGAR não é — leva o agente e todo o histórico. Exige digitar o nome, porque um clique
//     por engano num botão vermelho não deve custar o histórico inteiro.

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authedFetch } from "@/lib/auth/api";
import { exampleDefinition } from "@/lib/agentExample";
import { useMyRoles, canAdmin } from "@/lib/auth/roles";

type Version = {
  version: string | null;
  description: string | null;
  created_at: string | null;
  status: string | null;
};

type Session = {
  id: string | null;
  status: string | null;
  created_at: string | null;
  last_accessed_at: string | null;
  expires_at: string | null;
  version: string | null;
};

type Agent = {
  name: string;
  id: string | null;
  state: string | null;
  endpoint: string | null;
  version: Version | null;
  version_count: number;
  versions: Version[];
  // `null` (não `[]`) quando não foi possível ler: ver sessões exige permissão que ler o agente
  // não implica, e as duas situações precisam de mensagens diferentes.
  sessions: Session[] | null;
};

export function AgentDetail({ name }: { name: string }) {
  const t = useTranslations("agentDetail");
  const ta = useTranslations("agents");
  const tc = useTranslations("common");
  const router = useRouter();
  const roles = useMyRoles();
  const admin = canAdmin(roles);

  const [agent, setAgent] = useState<Agent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [doc, setDoc] = useState("");
  const [confirmName, setConfirmName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authedFetch(`/api/foundry/agents/${encodeURIComponent(name)}`, {
        cache: "no-store",
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setAgent(null);
        setError(body?.error ?? `${ta("errorTitle")} (HTTP ${r.status}).`);
      } else {
        setAgent(body);
      }
    } catch {
      setAgent(null);
      setError(tc("backendUnreachable"));
    } finally {
      setLoading(false);
    }
  }, [name, ta, tc]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Executa uma ação de escrita e mostra o resultado — sucesso ou o motivo da recusa. */
  const act = async (init: RequestInit, ok: string, then?: () => void) => {
    setBusy(true);
    setNotice(null);
    try {
      const r = await authedFetch(`/api/foundry/agents/${encodeURIComponent(name)}`, init);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setNotice(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      // Campo do documento que não chegou ao serviço é informação, não detalhe: sem isto a
      // pessoa acha que configurou algo que foi ignorado.
      const ignored = (body?.ignored_fields ?? []) as string[];
      setNotice(ignored.length ? `${ok} ${t("ignoredFields", { fields: ignored.join(", ") })}` : ok);
      then ? then() : void load();
    } catch {
      setNotice(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  const publish = () => {
    let parsed: unknown;
    try {
      // Aceita JSON direto. YAML exigiria uma dependência no browser para o mesmo resultado; o
      // exemplo mostra a forma, e quem cola YAML recebe uma mensagem que diz o que fazer.
      parsed = JSON.parse(doc);
    } catch {
      setNotice(t("invalidJson"));
      return;
    }
    void act(
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ definition: parsed }),
      },
      t("published"),
    );
  };

  const enabled = (agent?.state ?? "").toLowerCase().includes("enabled");

  return (
    <section className="stack">
      <header className="between">
        <div>
          <p className="t-xs muted-line">
            <Link href="/agents">{ta("title")}</Link>
          </p>
          <h2 className="page-title">{name}</h2>
          {agent?.version?.description && (
            <p className="page-sub">{agent.version.description}</p>
          )}
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

      {loading && !agent && !error && (
        <div className="skeleton-list" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton-row" />
          ))}
        </div>
      )}

      {error && (
        <div className="notice notice-block">
          <p className="notice-title">{ta("errorTitle")}</p>
          <p className="notice-body">{error}</p>
          <button type="button" className="btn" onClick={() => void load()}>
            {tc("retry")}
          </button>
        </div>
      )}

      {agent && (
        <>
          <div className="row">
            <span className={`pill ${enabled ? "ok" : "neutral"}`}>{agent.state ?? "—"}</span>
            <span className="t-sm muted-line">
              {t("versionCount", { count: agent.version_count })}
            </span>
          </div>

          <div className="stack-sm">
            <h3 className="section-title">{t("versionsTitle")}</h3>
            {agent.versions.length === 0 ? (
              <p className="muted t-sm">{t("noVersions")}</p>
            ) : (
              <div className="table-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>{t("colVersion")}</th>
                      <th>{t("colStatus")}</th>
                      <th>{t("colCreated")}</th>
                      <th>{t("colDescription")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* Mais recente primeiro: o topo da lista é o que está no ar. */}
                    {[...agent.versions].reverse().map((v) => (
                      <tr key={v.version ?? Math.random()}>
                        <td className="t-mono">{v.version ?? "—"}</td>
                        <td>
                          <span className="pill neutral">{v.status ?? "—"}</span>
                        </td>
                        <td className="t-sm">{v.created_at ?? "—"}</td>
                        <td className="t-sm">{v.description ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="stack-sm">
            <h3 className="section-title">{t("sessionsTitle")}</h3>
            {agent.sessions === null ? (
              // Não é "nenhuma sessão": é "não foi possível ler". Confundir os dois esconderia
              // falta de permissão atrás de uma tela vazia e tranquila.
              <p className="muted t-sm">{t("sessionsUnavailable")}</p>
            ) : agent.sessions.length === 0 ? (
              <p className="muted t-sm">{t("noSessions")}</p>
            ) : (
              <div className="table-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>{t("colSession")}</th>
                      <th>{t("colStatus")}</th>
                      <th>{t("colVersion")}</th>
                      <th>{t("colLastAccess")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agent.sessions.map((s) => (
                      <tr key={s.id ?? Math.random()}>
                        <td className="t-mono t-sm">{s.id ?? "—"}</td>
                        <td>
                          <span className="pill neutral">{s.status ?? "—"}</span>
                        </td>
                        <td className="t-mono t-sm">{s.version ?? "—"}</td>
                        <td className="t-sm">{s.last_accessed_at ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {admin && (
            <div className="stack-sm">
              <h3 className="section-title">{t("publishTitle")}</h3>
              <p className="muted t-sm">{t("publishHelp")}</p>
              <textarea
                className="acct-btn"
                rows={10}
                spellCheck={false}
                placeholder={exampleDefinition(t("exampleInstructions"))}
                value={doc}
                onChange={(e) => setDoc(e.target.value)}
              />
              <div className="row">
                <button
                  type="button"
                  className="btn btn-solid"
                  disabled={busy || !doc.trim()}
                  onClick={publish}
                >
                  {t("publishBtn")}
                </button>
                <div className="grow" />
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ action: enabled ? "disable" : "enable" }),
                      },
                      enabled ? t("disabled") : t("enabled"),
                    )
                  }
                >
                  {enabled ? t("disableBtn") : t("enableBtn")}
                </button>
              </div>

              {/* Apagar leva o histórico inteiro e não volta. Digitar o nome é o que separa a
                  intenção do clique acidental — um confirm() cumpre a formalidade e não a
                  intenção. */}
              <div className="notice notice-block">
                <p className="notice-title">{t("dangerTitle")}</p>
                <p className="notice-body">{t("dangerBody")}</p>
                <div className="row-tight">
                  <input
                    className="acct-btn grow"
                    placeholder={t("confirmPlaceholder", { name })}
                    value={confirmName}
                    onChange={(e) => setConfirmName(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn"
                    disabled={busy || confirmName !== name}
                    onClick={() =>
                      void act({ method: "DELETE" }, t("deleted"), () => router.push("/agents"))
                    }
                  >
                    {tc("delete")}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
