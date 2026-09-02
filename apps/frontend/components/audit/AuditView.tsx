"use client";

// A trilha de auditoria, visível (ADR-023).
//
// POR QUE ESTA TELA EXISTE, e o que ela NÃO é. Ela não é a prova — a prova é o pacote exportado,
// que se verifica sem este produto. Esta tela é o ACOMPANHAMENTO: responde "está sendo registrado?
// a cadeia está íntegra? faltou fechar algum dia?" para quem opera, sem precisar de curl.
//
// A distinção importa porque uma tela bonita de auditoria induz confiança em quem já confia no
// sistema que a desenha. Por isso o botão de exportar fica ao lado do estado, e o texto diz que
// é o pacote que vale contra terceiro.
//
// O QUE ELA MOSTRA COM DESTAQUE: o que FALTA. Uma trilha com eventos e zero âncoras está
// internamente consistente e sem fecho — e é exatamente o estado que passa despercebido se a
// tela só mostrar ✓ verde.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

type Chain = { ok: boolean; length: number; broken_at: number | null; reason: string };
type ScopeReport = { events: number; chain: Chain; anchors: number; unanchored: boolean };
type Report = {
  generated_at: string;
  scopes: Record<string, ScopeReport>;
  missing_proofs: string[];
};
type Evento = {
  seq: number; at: string; actor: string; kind: string;
  summary: string; ref: string; detail: Record<string, unknown>; hash: string;
};

export function AuditView() {
  const t = useTranslations("audit");
  const tc = useTranslations("common");
  const [report, setReport] = useState<Report | null>(null);
  const [escopo, setEscopo] = useState<string>("approvals");
  const [eventos, setEventos] = useState<Evento[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [erroTrilha, setErroTrilha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const r = await authedFetch("/api/audit?op=report", { cache: "no-store" });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(b?.error ?? `HTTP ${r.status}`);
        return;
      }
      setReport(b);
    } catch {
      setErro(tc("backendUnreachable"));
    }
  }, [tc]);

  const abrir = useCallback(async (s: string) => {
    setEscopo(s);
    setEventos(null);
    setErroTrilha(null);
    try {
      const r = await authedFetch(`/api/audit?op=trail&scope=${encodeURIComponent(s)}`, {
        cache: "no-store",
      });
      const b = await r.json().catch(() => ({}));
      if (r.ok) setEventos(b.events ?? []);
      else setErroTrilha(t("trailError"));
    } catch {
      setErroTrilha(t("trailError"));
    }
  }, [t]);

  useEffect(() => {
    void carregar();
  }, [carregar]);
  useEffect(() => {
    // Só na montagem. Trocar de escopo chama `abrir` diretamente, então `escopo` fora das
    // dependências é intencional: reagir a ele aqui abriria o escopo duas vezes.
    void abrir(escopo);
  }, []);

  const fechar = async (s: string) => {
    setBusy(true);
    setAviso(null);
    try {
      const r = await authedFetch(`/api/audit?scope=${encodeURIComponent(s)}`, { method: "POST" });
      const b = await r.json().catch(() => ({}));
      setAviso(
        r.ok
          ? b.written
            ? t("anchored", { date: b.date })
            : t("anchorRefused", { reason: b.refused || b.reason })
          : (b?.error ?? `HTTP ${r.status}`),
      );
      void carregar();
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
        {/* Exportar fica ao lado do estado: é o objeto que vale fora daqui. */}
        <a className="btn btn-solid" href="/api/audit?op=package" download>
          {t("export")}
        </a>
      </header>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}
      {aviso && (
        <div className="notice">
          <p className="notice-body">{aviso}</p>
        </div>
      )}

      {!erro && report === null && <p className="muted t-sm">{tc("loading")}</p>}

      {report && (
        <>
          <div className="grid g3">
            {Object.entries(report.scopes).map(([nome, s]) => (
              <button
                key={nome}
                type="button"
                className={`metric as-button${escopo === nome ? " on" : ""}`}
                onClick={() => void abrir(nome)}
              >
                <span className="metric-value num">{s.events}</span>
                <span className="metric-label">{t(`scope_${nome}`)}</span>
                <span className="t-xs">
                  {s.chain.ok ? (
                    <span className="ok-line">{t("chainOk")}</span>
                  ) : (
                    <span className="bad-line">{t("chainBroken", { seq: s.chain.broken_at ?? 0 })}</span>
                  )}
                </span>
                {/* O que falta, em destaque: consistente E sem fecho é o estado que passa
                    despercebido quando a tela só mostra verde. */}
                {s.unanchored && <span className="t-xs wait-line">{t("unanchored")}</span>}
              </button>
            ))}
          </div>

          <div className="row-tight">
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => void fechar(escopo)}
            >
              {busy ? t("closing") : t("closeDay", { scope: t(`scope_${escopo}`) })}
            </button>
            <span className="muted t-xs">{t("closeHelp")}</span>
          </div>

          {/* As provas que NÃO temos, ditas na tela e não só no pacote. */}
          <p className="t-xs wait-line">
            {t("missingProofs", { list: report.missing_proofs.join(", ") })}
          </p>
        </>
      )}

      <div className="stack-sm">
        <h3 className="section-title">{t("eventsIn", { scope: t(`scope_${escopo}`) })}</h3>
        {erroTrilha ? (
          <div className="notice notice-block">
            <p className="notice-body">{erroTrilha}</p>
          </div>
        ) : eventos === null ? (
          <p className="muted t-sm">{tc("loading")}</p>
        ) : eventos.length === 0 ? (
          <p className="muted t-sm">{t("noEvents")}</p>
        ) : (
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t("colWhen")}</th>
                  <th>{t("colActor")}</th>
                  <th>{t("colWhat")}</th>
                  <th>{t("colHash")}</th>
                </tr>
              </thead>
              <tbody>
                {[...eventos].reverse().map((e) => (
                  <tr key={e.hash}>
                    <td className="num">{e.seq}</td>
                    <td className="t-sm">{new Date(e.at).toLocaleString()}</td>
                    {/* O ator vem como `human:<oid>` / `process:<x>` — mostrado CRU porque é o
                        identificador que aparece no evento e no export; embelezá-lo aqui faria a
                        tela discordar do arquivo. */}
                    <td className="t-mono t-xs">{e.actor}</td>
                    <td className="t-sm">
                      {e.summary}
                      {e.ref && <span className="muted"> · {e.ref}</span>}
                    </td>
                    <td className="t-mono t-xs" title={e.hash}>
                      {e.hash.slice(0, 12)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
