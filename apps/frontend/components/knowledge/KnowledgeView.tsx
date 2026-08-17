"use client";

// Catálogo de bases de conhecimento — a segunda tela do produto que o PRODUCT.md descreve:
// "o que é meu", em vez das features que o time embutiu.
//
// A tela responde duas perguntas, e a segunda é a que o portal não responde bem:
//
//   1. quais bases existem e de que elas se alimentam;
//   2. QUAL FONTE NINGUÉM USA. Fonte que nenhuma base referencia é indexer rodando sozinho —
//      custo que não aparece em lugar nenhum até a fatura. O backend marca (`orphan`), e aqui
//      isso vira aviso visível em vez de um detalhe que só quem cruza as duas listas descobre.
//
// Três estados, como na tela de agentes, e a distinção entre "nada criado" e "não foi possível
// ler" continua valendo segurança: confundi-las esconderia falta de permissão atrás de uma tela
// vazia e tranquila.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { useMyRoles, canAdmin } from "@/lib/auth/roles";
import { CreateKnowledge } from "@/components/knowledge/CreateKnowledge";

type Base = {
  name: string;
  description: string | null;
  sources: string[];
  source_count: number;
};

type Source = {
  name: string;
  description: string | null;
  kind: string | null;
  orphan?: boolean;
};

export function KnowledgeView() {
  const t = useTranslations("knowledge");
  const tc = useTranslations("common");
  const [data, setData] = useState<{ bases: Base[]; sources: Source[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const roles = useMyRoles();
  const admin = canAdmin(roles);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await authedFetch("/api/foundry/knowledge", { cache: "no-store" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        // Erro de leitura NÃO vira lista vazia: `data` fica null e a tela diz o que houve.
        setData(null);
        setError(body?.error ?? `${t("errorTitle")} (HTTP ${r.status}).`);
      } else {
        setData({ bases: body.bases ?? [], sources: body.sources ?? [] });
      }
    } catch {
      setData(null);
      setError(tc("backendUnreachable"));
    } finally {
      setLoading(false);
    }
  }, [t, tc]);

  useEffect(() => {
    void load();
  }, [load]);

  const orphans = (data?.sources ?? []).filter((s) => s.orphan);

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

      {/* Esqueleto, não spinner: o carregamento preserva a forma do que vem, para a página não
          saltar quando os dados chegam. */}
      {loading && data === null && !error && (
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

      {!error && data && data.bases.length === 0 && data.sources.length === 0 && (
        <div className="empty">
          <p className="empty-title">{t("emptyTitle")}</p>
          <p className="empty-body">{t("emptyBody")}</p>
        </div>
      )}

      {/* Criar vem antes das listas para quem PODE criar: numa tela vazia, a lista não é o
          conteúdo — o próximo passo é. */}
      {admin && <CreateKnowledge onCreated={() => void load()} />}

      {/* O aviso vem ANTES das tabelas: é a informação acionável da tela, e enterrá-lo embaixo
          de duas listas faria com que só quem já sabia procurar o encontrasse. */}
      {!error && orphans.length > 0 && (
        <div className="notice notice-wait">
          <p className="notice-title">{t("orphanTitle", { count: orphans.length })}</p>
          <p className="notice-body">{t("orphanBody")}</p>
          <p className="t-mono t-sm">{orphans.map((s) => s.name).join(" · ")}</p>
        </div>
      )}

      {!error && data && data.bases.length > 0 && (
        <div className="stack-sm">
          <h3 className="section-title">{t("basesTitle")}</h3>
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t("colName")}</th>
                  <th>{t("colSources")}</th>
                  <th className="right">{t("colSourceCount")}</th>
                </tr>
              </thead>
              <tbody>
                {data.bases.map((b) => (
                  <tr key={b.name}>
                    <td>
                      <span className="strong">{b.name}</span>
                      {b.description && <p className="t-xs muted-line">{b.description}</p>}
                    </td>
                    <td className="t-mono t-sm">{b.sources.join(" · ") || "—"}</td>
                    <td className="right num">{b.source_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!error && data && data.sources.length > 0 && (
        <div className="stack-sm">
          <h3 className="section-title">{t("sourcesTitle")}</h3>
          <div className="table-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t("colName")}</th>
                  <th>{t("colKind")}</th>
                  <th>{t("colUsage")}</th>
                </tr>
              </thead>
              <tbody>
                {data.sources.map((s) => (
                  <tr key={s.name}>
                    <td>
                      <span className="strong">{s.name}</span>
                    </td>
                    {/* `kind` é nome de tipo do serviço (azureBlob, searchIndex): não se traduz,
                        é o que a pessoa vai procurar na documentação. */}
                    <td className="t-mono t-sm">{s.kind ?? "—"}</td>
                    <td>
                      <span className={`pill ${s.orphan ? "wait" : "ok"}`}>
                        {s.orphan ? t("orphanPill") : t("inUsePill")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
