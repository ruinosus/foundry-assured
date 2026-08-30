"use client";

// Criar um copiloto — pelo mesmo motor que ele mesmo vai usar.
//
// O formulário é `agents/assured/flows/copilot.md`, um `type: formflow` como os outros três. Não
// é elegância: é o teste do motor. Se ele não desse conta de descrever o próprio produto, não
// daria conta do quarto domínio que alguém quisesse acrescentar.
//
// A SAÍDA É O DOCUMENTO, e isso é o desenho, não uma etapa faltando — ver `lib/copilot-doc.ts`.

import { useTranslations } from "next-intl";
import { useState } from "react";
import Link from "next/link";
import { FormFlowFields, FormFlowProposalTool, useFormFlow } from "@/components/formflow/FormFlow";
import { useManifest } from "@/lib/formflow/load";
import { caminhoDoDocumento, montarDocumento } from "@/lib/copilot-doc";
import type { FormFlowManifest } from "@/lib/formflow/types";

export function CopilotNew() {
  const t = useTranslations("copilots");
  const tf = useTranslations("formflow");
  const m = useManifest("copilot");

  if (m.estado === "ok") return <Form manifest={m.manifest} />;
  return (
    <section className="card stack-sm">
      <h3 className="section-title">{t("novoTitulo")}</h3>
      {m.estado === "carregando" ? (
        <p className="muted t-sm">{tf("carregando")}</p>
      ) : (
        <div className="notice notice-block">
          <p className="notice-body">{tf(`erro_${m.motivo}`, { detail: m.detalhe })}</p>
        </div>
      )}
    </section>
  );
}

function Form({ manifest }: { manifest: FormFlowManifest }) {
  const t = useTranslations("copilots");
  const tf = useTranslations("formflow");
  const { estado, set, regraDoCampo, aplicarProposta, catalogos } = useFormFlow(manifest);
  const [copiado, setCopiado] = useState(false);

  const bloqueio = estado.bloqueio;
  const obrigatorias = estado.secoes.filter((s) => !s.opcional);
  const documento = montarDocumento(estado.valores);
  const caminho = caminhoDoDocumento(estado.valores);

  return (
    <section className="card wizard">
      <FormFlowProposalTool
        manifest={manifest}
        valores={estado.valores}
        regraDoCampo={regraDoCampo}
        onAccept={aplicarProposta}
      />

      <header className="between wizard-head">
        <div className="stack-sm">
          <h3 className="section-title">{t("novoTitulo")}</h3>
          <p className="muted t-sm">{t("novoSubtitulo")}</p>
        </div>
        <Link className="btn" href="/copilots">
          {t("voltarCatalogo")}
        </Link>
      </header>

      {bloqueio && <p className="t-xs muted-line wizard-blocked">{bloqueio}</p>}

      <div className="wizard-body">
        <nav className="wizard-rail" aria-label={tf("stepsLabel")}>
          <p className="wizard-rail-head">
            <span className="t-2xs muted-line">{tf("progresso")}</span>
            <span className="t-sm strong">
              {tf("progressoContagem", {
                done: obrigatorias.filter((s) => !s.pendencia).length,
                total: obrigatorias.length,
              })}
            </span>
          </p>
          <ol className="wizard-rail-list">
            {estado.secoes.map((sec, i) => (
              <li key={sec.id}>
                <a
                  href={`#w-${sec.id}`}
                  className={`wizard-rail-item ${sec.pendencia ? "pending" : sec.opcional ? "optional" : "done"}`}
                >
                  <span className="wizard-rail-mark" aria-hidden>
                    {sec.pendencia ? String(i + 1) : sec.opcional ? "·" : "✓"}
                  </span>
                  <span className="wizard-rail-text">
                    <span className="wizard-rail-title">{sec.titulo}</span>
                    <span className="wizard-rail-note">{sec.pendencia ?? sec.resumo}</span>
                  </span>
                </a>
              </li>
            ))}
          </ol>

          {/* POR QUE NÃO HÁ BOTÃO DE PUBLICAR, dito onde a pessoa procuraria por ele. Um botão
              ausente sem explicação é lido como funcionalidade que falta; com a explicação, é
              lido como a decisão que é. */}
          <div className="wizard-prov">
            <p className="t-2xs muted-line">{t("saidaTitulo")}</p>
            <p className="t-2xs muted-line">{t("saidaExplicacao")}</p>
          </div>
        </nav>

        <div className="wizard-form">
          <FormFlowFields
            manifest={manifest}
            valores={estado.valores}
            set={set}
            regraDoCampo={regraDoCampo}
            catalogos={catalogos}
            origens={estado.origens}
          />

          <section id="w-review" className="wizard-section">
            <h4 className="wizard-section-title">{tf("revisao")}</h4>
            <dl className="review">
              {estado.revisao.map((l) => (
                <div key={l.label}>
                  <dt>{l.label}</dt>
                  <dd>{l.texto}</dd>
                </div>
              ))}
            </dl>

            <h4 className="wizard-section-title">{t("documentoTitulo")}</h4>
            <p className="muted t-xs">
              {t("documentoCaminho")} <code>{caminho}</code>
            </p>
            <div className="row-tight">
              <button
                type="button"
                className="btn"
                disabled={bloqueio !== null}
                title={bloqueio ?? undefined}
                onClick={() => {
                  // `navigator.clipboard` pode não existir (contexto não seguro) ou ser negado.
                  // O documento continua na tela para seleção manual — copiar é atalho, não a
                  // única saída, e um botão que falha calado faria a pessoa achar que copiou.
                  const area = navigator.clipboard;
                  void area?.writeText(documento).then(() => setCopiado(true)).catch(() => setCopiado(false));
                }}
              >
                {copiado ? t("copiado") : t("copiar")}
              </button>
            </div>
            <pre className="doc-preview">{documento}</pre>
          </section>
        </div>
      </div>
    </section>
  );
}
