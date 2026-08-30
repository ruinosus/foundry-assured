"use client";

// O COPILOTO COMO RECURSO — não como arquivo.
//
// A tentação era fazer "a tela de editar o manifesto". O mock é explícito contra isso, e a razão
// se sustenta sozinha: *"editar o manifesto é uma operação sobre a DEFINIÇÃO — por isso ela vive
// numa aba, com versão e gate, em vez de ser a tela inteira."*
//
// O recurso tem estado, alvos, procedência de decisão e fim de vida. O documento é UMA das abas.
// Uma tela que fosse só o editor faria a definição parecer o produto, e a pessoa que precisa
// saber "onde este copiloto atua e o que ele já escreveu" abriria um editor de YAML.
//
// O QUE ESTA TELA AINDA NÃO TEM, e é deliberado: versões, atividade e custo. Os três dependem de
// coisas que não existem no backend (versionamento de copiloto, trilha por copiloto, medição por
// área). Mostrá-los vazios ensinaria que o produto os tem — e um painel que promete o que não
// mede é pior que um painel a menos.

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { recursosDoMotor, type Copilot } from "@/lib/copilot";

type Aba = "geral" | "alvos" | "definicao";

export function CopilotResource({ nome }: { nome: string }) {
  const t = useTranslations("copilots");
  const tc = useTranslations("common");
  const [copiloto, setCopiloto] = useState<Copilot | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<Aba>("geral");

  useEffect(() => {
    let vivo = true;
    void (async () => {
      try {
        const r = await authedFetch(`/api/copilots/${encodeURIComponent(nome)}`, { cache: "no-store" });
        const b = await r.json().catch(() => ({}));
        if (!vivo) return;
        if (r.ok) setCopiloto(b as Copilot);
        else setErro(String(b?.detail ?? b?.error ?? `HTTP ${r.status}`));
      } catch {
        if (vivo) setErro(tc("backendUnreachable"));
      }
    })();
    return () => {
      vivo = false;
    };
  }, [nome, tc]);

  if (erro) {
    return (
      <div className="notice notice-block">
        <p className="notice-body">{erro}</p>
      </div>
    );
  }
  if (!copiloto) return <p className="muted t-sm">{tc("loading")}</p>;

  const problemas = copiloto.target_problems ?? [];
  const recursos = recursosDoMotor(copiloto, t as never);
  const usa = recursos.filter((r) => r.usa);
  const naoPrecisa = recursos.filter((r) => !r.usa);

  return (
    <section className="card stack-sm">
      <header className="between">
        <div className="stack-sm">
          <h3 className="section-title">{copiloto.title ?? copiloto.name}</h3>
          <p className="muted t-sm">{copiloto.description}</p>
          <p className="t-2xs muted-line">
            <code>copilots/{copiloto.name}</code>
            {copiloto.engine?.agent && ` · ${t("sobreAgente", { agent: copiloto.engine.agent })}`}
          </p>
        </div>
      </header>

      {/* OS PROBLEMAS DOS ALVOS APARECEM NO TOPO, sempre — não escondidos na aba de alvos. Um
          copiloto que declara escrever num campo inexistente está quebrado, e quem abre a tela
          precisa saber disso antes de decidir qualquer outra coisa. */}
      {problemas.length > 0 && (
        <div className="notice notice-block">
          <p className="notice-body">{t("alvosQuebrados", { count: problemas.length })}</p>
          <ul className="stack-sm">
            {problemas.map((p) => (
              <li key={p} className="t-xs">
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      <nav className="tabs" aria-label={t("abas")}>
        {(["geral", "alvos", "definicao"] as const).map((a) => (
          <button
            key={a}
            type="button"
            className={`tab ${aba === a ? "on" : ""}`}
            aria-current={aba === a}
            onClick={() => setAba(a)}
          >
            {t(`aba_${a}`)}
          </button>
        ))}
      </nav>

      {aba === "geral" && (
        <div className="copilot-grid">
          <dl className="review">
            <div>
              <dt>{t("ondeAtua")}</dt>
              <dd>
                {copiloto.surface?.screens?.length
                  ? t("ondeAtuaTexto", {
                      mount: copiloto.surface.mount ?? "—",
                      screens: copiloto.surface.screens.join(", "),
                    })
                  : t("semSuperficie")}
              </dd>
            </div>
            <div>
              <dt>{t("quemExecuta")}</dt>
              <dd>
                {t("quemExecutaTexto", {
                  agent: copiloto.engine?.agent ?? "—",
                  runtime: copiloto.engine?.runtime ?? "—",
                })}
              </dd>
            </div>
            <div>
              <dt>{t("ondePara")}</dt>
              <dd>{copiloto.policy ? t("politicaTexto", { name: copiloto.policy }) : t("semPolitica")}</dd>
            </div>
          </dl>

          {/* A MATRIZ. Dois lados, nenhuma nota — ver `lib/copilot.ts` para por que não há
              fração: "não precisa" não é "não cumpre". */}
          <div className="engine-matrix">
            <p className="t-2xs muted-line">{t("matrizTitulo")}</p>
            <ul className="engine-list">
              {usa.map((r) => (
                <li key={r.id} className="engine-item usa">
                  <span className="engine-mark" aria-hidden>
                    ✓
                  </span>
                  <span className="engine-text">
                    <b className="t-xs">{t(`recurso_${r.id}`)}</b>
                    <span className="t-2xs muted-line">{r.detalhe}</span>
                  </span>
                </li>
              ))}
            </ul>
            {naoPrecisa.length > 0 && (
              <>
                <p className="t-2xs muted-line engine-sep">{t("naoPrecisa")}</p>
                <ul className="engine-list">
                  {naoPrecisa.map((r) => (
                    <li key={r.id} className="engine-item">
                      <span className="engine-mark" aria-hidden>
                        ·
                      </span>
                      <span className="engine-text">
                        <b className="t-xs">{t(`recurso_${r.id}`)}</b>
                        <span className="t-2xs muted-line">{r.detalhe}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="t-2xs muted-line engine-note">{t("matrizNota")}</p>
          </div>
        </div>
      )}

      {aba === "alvos" && (
        <div className="scroll-x">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("colFormulario")}</th>
                <th>{t("colCampos")}</th>
                <th>{t("colRegra")}</th>
              </tr>
            </thead>
            <tbody>
              {(copiloto.targets ?? []).map((alvo) => (
                <tr key={alvo.flow}>
                  <td>
                    <code className="t-xs">{alvo.flow}</code>
                  </td>
                  <td>
                    <ul className="source-chips">
                      {(alvo.writes ?? []).map((c) => (
                        <li key={c} className="source-chip">
                          {c}
                        </li>
                      ))}
                    </ul>
                  </td>
                  <td className="t-xs muted-line">{alvo.validateAgainst ?? "—"}</td>
                </tr>
              ))}
              {!(copiloto.targets ?? []).length && (
                <tr>
                  <td colSpan={3} className="muted t-xs">
                    {t("semAlvos")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {aba === "definicao" && (
        <div className="stack-sm">
          {/* SOMENTE LEITURA, e o motivo é dito: documento publicado não é editado. Um botão de
              salvar aqui contradiria a regra que o resto do produto sustenta. */}
          <p className="muted t-xs">{t("definicaoSomenteLeitura")}</p>
          <pre className="doc-preview">{JSON.stringify(semRuido(copiloto), null, 2)}</pre>
        </div>
      )}
    </section>
  );
}

/** O documento sem o que a API acrescentou. `target_problems` é resultado de verificação, não
 *  parte do manifesto — mostrá-lo aqui faria a aba mentir sobre o que está no arquivo. */
function semRuido(c: Copilot): Record<string, unknown> {
  const { target_problems: _ignorado, ...doc } = c;
  return doc;
}
