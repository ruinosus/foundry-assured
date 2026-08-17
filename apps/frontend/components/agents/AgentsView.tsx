"use client";

// Catálogo de agentes do Foundry — a primeira tela do produto que o PRODUCT.md descreve:
// "o que é meu", em vez das features que o time embutiu.
//
// A tela tem três estados e os três importam igualmente. O register `product` é explícito de
// que estado vazio ensina a interface, e aqui há uma distinção que vale segurança: "nenhum
// agente criado" e "não foi possível ler" são coisas diferentes, e confundi-las esconderia
// falta de permissão atrás de uma tela vazia e tranquila.

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

type AgentVersion = {
  version: string | null;
  description: string | null;
  created_at: string | null;
  status: string | null;
};

type Agent = {
  name: string;
  id: string | null;
  state: string | null;
  kind: string | null;
  endpoint: string | null;
  version: AgentVersion | null;
  version_count: number;
};

/** Estado do agente vira a semântica da interface: habilitado passa, desabilitado é neutro. */
function stateTone(state: string | null): string {
  const s = (state ?? "").toLowerCase();
  if (s.includes("enabled") || s.includes("active")) return "ok";
  if (s.includes("disabled") || s.includes("failed")) return "bad";
  return "neutral";
}

function whenLabel(iso: string | null, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  // Locale do usuário, não cravado: traduzir o texto e deixar a data em dd/mm quando a pessoa
  // escolheu inglês é o erro clássico de i18n — a metade que ninguém revisa.
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString(locale);
}

export function AgentsView() {
  const t = useTranslations("agents");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authedFetch("/api/foundry/agents", { cache: "no-store" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        // Um erro de leitura NÃO vira lista vazia: `agents` fica null e a tela diz o que houve.
        setAgents(null);
        setError(data?.error ?? `${t("errorTitle")} (HTTP ${r.status}).`);
      } else {
        setAgents(data.agents ?? []);
      }
    } catch {
      setAgents(null);
      setError(t("errorUnreachable"));
    } finally {
      setLoading(false);
    }
  }, [t]);

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

      {/* Esqueleto, não spinner no meio do conteúdo: o register pede que o carregamento
          preserve a forma do que vem, para a página não saltar quando os dados chegam. */}
      {loading && agents === null && !error && (
        <div className="skeleton-list" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton-row" />
          ))}
        </div>
      )}

      {/* Falha de leitura. Diz o que houve e oferece a ação — nunca se disfarça de "vazio". */}
      {error && (
        <div className="notice notice-block">
          <p className="notice-title">{t("errorTitle")}</p>
          <p className="notice-body">{error}</p>
          <button type="button" className="btn" onClick={() => void load()}>
            {tc("retry")}
          </button>
        </div>
      )}

      {/* Vazio de verdade: o serviço respondeu, e não há nada. Ensina o próximo passo em vez de
          anunciar a ausência. */}
      {!error && agents !== null && agents.length === 0 && (
        <div className="empty">
          <p className="empty-title">{t("emptyTitle")}</p>
<p className="empty-body">{t("emptyBody")}</p>
        </div>
      )}

      {!error && agents !== null && agents.length > 0 && (
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("colName")}</th>
                <th>{t("colState")}</th>
                <th>{t("colVersion")}</th>
                <th className="right">{t("colVersions")}</th>
                <th>{t("colPublished")}</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.name}>
                  <td>
                    <Link className="strong" href={`/agents/${encodeURIComponent(a.name)}`}>
                      {a.name}
                    </Link>
                    {a.version?.description && (
                      <p className="t-xs muted-line">{a.version.description}</p>
                    )}
                  </td>
                  <td>
                    <span className={`pill ${stateTone(a.state)}`}>{a.state ?? "—"}</span>
                  </td>
                  <td className="t-mono">{a.version?.version ?? "—"}</td>
                  {/* O recurso é versionado; a contagem é o que torna isso visível na lista. */}
                  <td className="right num">{a.version_count}</td>
                  <td className="t-sm">{whenLabel(a.version?.created_at ?? null, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
