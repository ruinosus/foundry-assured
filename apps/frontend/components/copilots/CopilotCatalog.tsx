"use client";

// O catálogo: quem existe, onde atua, e o que escreve.
//
// A COLUNA "ESCREVE" É A QUE IMPORTA numa lista de copilotos. Um catálogo que mostrasse só nome e
// descrição serviria para achar; este serve para responder a pergunta que se faz olhando a lista:
// *quais deles podem mexer nos meus formulários?* Um copiloto sem alvo é dito como tal — ele
// conversa e não escreve, o que é uma configuração legítima e não uma lacuna.

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import Link from "next/link";
import { authedFetch } from "@/lib/auth/api";
import type { Copilot } from "@/lib/copilot";

export function CopilotCatalog() {
  const t = useTranslations("copilots");
  const tc = useTranslations("common");
  const [itens, setItens] = useState<Copilot[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    void (async () => {
      try {
        const r = await authedFetch("/api/copilots", { cache: "no-store" });
        const b = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(String(b?.detail ?? b?.error ?? r.status));
        // Uma leitura por copiloto: a lista devolve nomes, e a tabela precisa dos alvos. São
        // poucos e a alternativa seria um endpoint que devolve tudo — que é o mesmo trabalho,
        // feito no servidor, para uma tela que ainda não tem escala para pedi-lo.
        const nomes = (b?.copilots ?? []) as string[];
        const docs = await Promise.all(
          nomes.map(async (n) => {
            const rr = await authedFetch(`/api/copilots/${encodeURIComponent(n)}`, { cache: "no-store" });
            return rr.ok ? ((await rr.json()) as Copilot) : ({ name: n } as Copilot);
          }),
        );
        if (vivo) setItens(docs);
      } catch (e) {
        if (vivo) setErro(String(e instanceof Error ? e.message : e));
      }
    })();
    return () => {
      vivo = false;
    };
  }, []);

  if (erro) {
    return (
      <section className="card stack-sm">
        <h3 className="section-title">{t("titulo")}</h3>
        <div className="notice notice-block">
          <p className="notice-body">{t("erroCatalogo", { motivo: erro })}</p>
        </div>
      </section>
    );
  }
  if (!itens) return <p className="muted t-sm">{tc("loading")}</p>;

  return (
    <section className="card stack-sm">
      <header className="between">
        <div className="stack-sm">
          <h3 className="section-title">{t("titulo")}</h3>
          <p className="muted t-sm">{t("subtitulo")}</p>
        </div>
        <Link className="btn btn-solid" href="/copilots/novo">
          {t("novo")}
        </Link>
      </header>

      {itens.length === 0 ? (
        <p className="muted t-sm">{t("vazio")}</p>
      ) : (
        <div className="scroll-x">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("colCopiloto")}</th>
                <th>{t("colEscreve")}</th>
                <th>{t("colOnde")}</th>
                <th>{t("colRuntime")}</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((c) => {
                // QUALIFICADO por formulário (`agent.name`), e não só o nome do campo. Três
                // `name` seguidos numa linha não dizem nada — e, como chave de lista, produziam
                // "two children with the same key" no console. Um bug, dois sintomas: a coluna
                // ilegível e o aviso do React. Encontrado rodando a tela; `tsc`, `lint` e `build`
                // passavam, porque nenhum deles renderiza.
                const campos = (c.targets ?? []).flatMap((x) =>
                  (x.writes ?? []).map((w) => `${x.flow}.${w}`),
                );
                const quebrado = (c.target_problems ?? []).length > 0;
                return (
                  <tr key={c.name}>
                    <td>
                      <Link href={`/copilots/${encodeURIComponent(c.name)}`}>{c.title ?? c.name}</Link>
                      {/* Um copiloto com alvo quebrado é marcado NA LISTA: quem varre o catálogo
                          precisa ver o que está quebrado sem abrir cada um. */}
                      {quebrado && <span className="t-2xs bad-line"> · {t("quebrado")}</span>}
                      <div className="t-2xs muted-line">{c.description}</div>
                    </td>
                    <td>
                      {campos.length ? (
                        <ul className="source-chips">
                          {campos.map((f) => (
                            <li key={f} className="source-chip">
                              {f}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="t-xs muted-line">{t("soLeitura")}</span>
                      )}
                    </td>
                    <td className="t-xs">{(c.surface?.screens ?? []).join(", ") || "—"}</td>
                    <td className="t-xs">{c.engine?.runtime ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
