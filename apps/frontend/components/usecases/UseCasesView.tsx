"use client";

// Casos de uso — a porta de entrada de quem é de negócio.
//
// O QUE ISTO CORRIGE: "ninguém de negócio consegue ler essa lista imensa de agents". E o problema
// não era a quantidade — `triage`, `retrieve`, `resolve` são PEÇAS. Quem é de negócio procura "o
// helpdesk", e o helpdesk estava dissolvido em seis linhas técnicas. Aqui ele volta a ser uma
// coisa só, com as peças visíveis quando alguém quiser.
//
// O cartão mostra o FLUXO, não a contagem. "Triagem → Buscar na base → Redigir resposta" diz o
// que o assistente faz; "3 agentes" não diz nada a quem não sabe o que é um agente.

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

type Step = {
  id: string | null;
  kind: string;
  label: string | null;
  agent: string | null;
  waits_for_human: boolean;
};

type UseCase = {
  id: string;
  name: string;
  description: string;
  agents: { name: string; state: string | null; version: string | null; runtime: string | null }[];
  steps: Step[];
  has_flow: boolean;
  runtime: string;
  reason?: string;
};

export function UseCasesView() {
  const t = useTranslations("useCases");
  const tc = useTranslations("common");
  const [cases, setCases] = useState<UseCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authedFetch("/api/usecases", { cache: "no-store" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setCases(null);
        setError(body?.error ?? `${t("errorTitle")} (HTTP ${r.status}).`);
      } else {
        setCases(body.use_cases ?? []);
        // O backend manda `reason` quando leu o repositório mas não o serviço — a lista aparece
        // incompleta, e dizer isso é melhor que mostrar menos casos sem explicar.
        const motivo = (body.use_cases ?? []).find((c: UseCase) => c.reason)?.reason;
        if (motivo) setError(motivo);
      }
    } catch {
      setCases(null);
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

      {loading && cases === null && !error && (
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

      {!error && cases !== null && cases.length === 0 && (
        <div className="empty">
          <p className="empty-title">{t("emptyTitle")}</p>
          {/* Um caso existe porque há agente publicado — se a lista está vazia, o ingest não
              rodou. O conselho aponta para a causa, não para um botão genérico. */}
          <p className="empty-body">{t("emptyBody")}</p>
        </div>
      )}

      {cases !== null && cases.length > 0 && (
        <div className="grid">
          {cases.map((c) => (
            <Link key={c.id} href={`/usecases/${encodeURIComponent(c.id)}`} className="card usecase-card">
              <header className="between">
                <h3 className="usecase-name">{c.name}</h3>
                {/* Onde executa, em palavras de negócio: quem lê isto não precisa saber o que é
                    um harness — precisa saber se roda no serviço ou aqui. */}
                <span className={`pill ${c.runtime === "foundry" ? "ok" : "neutral"}`}>
                  {t(`runtime_${c.runtime}`, { fallback: c.runtime })}
                </span>
              </header>

              {c.description && <p className="t-sm muted-line">{c.description}</p>}

              {/* O FLUXO é o conteúdo do cartão. Uma contagem de agentes não diz o que o
                  assistente faz; a sequência dos passos diz. */}
              {c.steps.length > 0 ? (
                <ol className="usecase-steps">
                  {c.steps.map((s, i) => (
                    <li key={s.id ?? i} className={s.waits_for_human ? "waits" : ""}>
                      {s.label}
                      {s.waits_for_human && <span className="t-xs"> · {t("waitsForHuman")}</span>}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="muted t-sm">{t("singleStep")}</p>
              )}

              <footer className="t-xs muted-line">
                {t("piecesCount", { count: c.agents.length })}
              </footer>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
