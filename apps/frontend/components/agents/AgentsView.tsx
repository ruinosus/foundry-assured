"use client";

// Catálogo de agentes do Foundry — a primeira tela do produto que o PRODUCT.md descreve:
// "o que é meu", em vez das features que o time embutiu.
//
// A tela tem três estados e os três importam igualmente. O register `product` é explícito de
// que estado vazio ensina a interface, e aqui há uma distinção que vale segurança: "nenhum
// agente criado" e "não foi possível ler" são coisas diferentes, e confundi-las esconderia
// falta de permissão atrás de uma tela vazia e tranquila.

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

function whenLabel(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

export function AgentsView() {
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
        setError(data?.error ?? `Não foi possível ler o catálogo (HTTP ${r.status}).`);
      } else {
        setAgents(data.agents ?? []);
      }
    } catch {
      setAgents(null);
      setError("Não foi possível falar com o serviço.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="stack">
      <header className="between">
        <div>
          <h2 className="page-title">Agentes</h2>
          <p className="page-sub">
            Os agentes deste projeto no Microsoft Foundry. Criar e publicar versões acontece
            aqui — sem abrir o portal.
          </p>
        </div>
        <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
          {loading ? "Atualizando…" : "Atualizar"}
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
          <p className="notice-title">Não foi possível ler o catálogo</p>
          <p className="notice-body">{error}</p>
          <button type="button" className="btn" onClick={() => void load()}>
            Tentar de novo
          </button>
        </div>
      )}

      {/* Vazio de verdade: o serviço respondeu, e não há nada. Ensina o próximo passo em vez de
          anunciar a ausência. */}
      {!error && agents !== null && agents.length === 0 && (
        <div className="empty">
          <p className="empty-title">Nenhum agente ainda</p>
          <p className="empty-body">
            Um agente reúne instruções, ferramentas e uma base de conhecimento. Quando você
            publicar o primeiro, ele aparece aqui com o histórico de versões.
          </p>
        </div>
      )}

      {!error && agents !== null && agents.length > 0 && (
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Agente</th>
                <th>Estado</th>
                <th>Versão</th>
                <th className="right">Versões</th>
                <th>Publicada em</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.name}>
                  <td>
                    <span className="strong">{a.name}</span>
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
                  <td className="t-sm">{whenLabel(a.version?.created_at ?? null)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
