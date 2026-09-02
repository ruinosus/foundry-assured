"use client";

// Os assistentes de TELA — e se eles ajudam de verdade.
//
// POR QUE ESTA TELA É SEPARADA DE "CASOS DE USO". Um assistente de tela não atende ninguém: ele
// ajuda alguém a preencher um formulário. Ele não tem conversa atendida, nem chamado evitado, nem
// economia estimada — as métricas de caso de uso não se aplicam, e forçá-lo naquela lista faria
// os números de lá deixarem de significar o que significam.
//
// O QUE ELE TEM É OUTRA COISA, e é medível: proposta feita, proposta usada, proposta CORRIGIDA.
//
// A DISTINÇÃO QUE ESTA TELA EXISTE PARA MOSTRAR: aproveitamento alto com edição alta não é
// sucesso. Um assistente cujas propostas são sempre corrigidas está sendo TOLERADO — a pessoa
// aproveita o rascunho porque é mais rápido que começar do zero, não porque ele acertou. Um
// painel que mostrasse só "75% de aproveitamento" esconderia exatamente isso, e é por isso que as
// duas taxas aparecem lado a lado, com a de edição legível como aviso quando sobe.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

type Stats = {
  total: number;
  by_outcome: { accepted: number; edited: number; discarded: number };
  used_rate: number | null;
  edited_rate: number | null;
  with_sources: number;
  by_field: Record<string, number>;
};

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

export function AssistantsView() {
  const t = useTranslations("assistants");
  const tc = useTranslations("common");
  const [dados, setDados] = useState<Stats | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setErro(null);
    try {
      const r = await authedFetch("/api/builder-assist", { cache: "no-store" });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(b?.error ?? `HTTP ${r.status}`);
        return;
      }
      setDados(b);
    } catch {
      setErro(tc("backendUnreachable"));
    }
  }, [tc]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Edição acima disto vira aviso. Não é um limiar de ciência: é o ponto em que "quase sempre
  // precisa de conserto" deixa de ser detalhe e passa a ser o fato principal sobre o assistente.
  const muitaEdicao = (dados?.edited_rate ?? 0) > 0.5;

  return (
    <section className="stack">
      <header>
        <h2 className="page-title">{t("title")}</h2>
        <p className="page-sub">{t("subtitle")}</p>
      </header>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}

      {!erro && dados === null && <p className="muted t-sm">{tc("loading")}</p>}

      {dados && dados.total === 0 && <p className="muted t-sm">{t("empty")}</p>}

      {dados && dados.total > 0 && (
        <>
          <p className="lead-in">{t("builderTitle")}</p>
          <div className="grid g3">
            <div className="metric">
              <span className="metric-value num">{dados.total}</span>
              <span className="metric-label">{t("proposals")}</span>
            </div>
            <div className="metric">
              <span className="metric-value num">{pct(dados.used_rate)}</span>
              <span className="metric-label">{t("usedRate")}</span>
              <span className="t-xs muted-line">
                {t("usedDetail", {
                  accepted: dados.by_outcome.accepted,
                  edited: dados.by_outcome.edited,
                })}
              </span>
            </div>
            <div className="metric">
              {/* A taxa que qualifica a anterior. Marcada quando sobe, porque é aí que ela deixa
                  de ser detalhe. */}
              <span className={`metric-value num${muitaEdicao ? " wait-line" : ""}`}>
                {pct(dados.edited_rate)}
              </span>
              <span className="metric-label">{t("editedRate")}</span>
              <span className="t-xs muted-line">{t("editedHelp")}</span>
            </div>
          </div>

          {muitaEdicao && (
            <div className="notice notice-wait">
              <p className="notice-body">{t("toleratedWarning")}</p>
            </div>
          )}

          <p className="t-sm muted-line">
            {t("withSources", { n: dados.with_sources, total: dados.total })}
          </p>

          <div className="stack-sm">
            <h3 className="section-title">{t("byField")}</h3>
            <div className="table-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>{t("colField")}</th>
                    <th>{t("colCount")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(dados.by_field).map(([campo, n]) => (
                    <tr key={campo}>
                      <td className="t-mono t-sm">{campo}</td>
                      <td className="num">{n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* De onde vêm os números: da trilha, não de um contador. Dizer isso na tela é o que
              permite a alguém conferir. */}
          <p className="t-xs muted-line">{t("source")}</p>
        </>
      )}
    </section>
  );
}
