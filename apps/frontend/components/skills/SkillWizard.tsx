"use client";

// Wizard de skill — sobre o motor de FormFlow e o executor de plano.
//
// O QUE SAIU DAQUI. Campos, rótulos, regras, revisão e a ORDEM das operações eram código neste
// arquivo. Viraram `apps/backend/agents/assured/flows/skill.md`. O que ficou é o que o manifesto
// declara mas não sabe executar: o CORPO de cada requisição.
//
// A SKILL É O CASO QUE MOTIVOU O EXECUTOR. Publicar são DUAS chamadas — criar a skill com as
// instruções inline, depois subir o bundle de arquivos — e a ordem não é preferência: os arquivos
// são uma versão da skill, então a skill precisa existir. Quando a segunda falha, a skill EXISTE.
// Uma tela que dissesse só "erro" faria a pessoa tentar de novo, e a segunda tentativa falharia na
// PRIMEIRA operação, agora por nome duplicado, com uma mensagem sem relação com o problema.
//
// `requires: [create_skill]` e `onFailure: partialSucceeded` estão no manifesto; quem os honra é
// `lib/formflow/plan.ts`, e o resultado parcial é dito na tela — com o plano guardado, para que a
// retentativa comece de onde parou.
//
// Duas validações vivem aqui E no backend, de propósito: nome de recurso e nome de arquivo. O
// backend é a fronteira real (a interface não é fronteira de segurança); a tela existe para que
// erro de digitação tenha resposta imediata, em vez de uma viagem até o Azure.

import { useTranslations } from "next-intl";
import { useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { FormFlowFields, FormFlowProposalTool, useFormFlow } from "@/components/formflow/FormFlow";
import { useManifest } from "@/lib/formflow/load";
import { executarPlano, resolverPath, type ResultadoPlano } from "@/lib/formflow/plan";
import { serializeProvenance } from "@/lib/okf";
import type { FormFlowManifest, Operacao } from "@/lib/formflow/types";

export function SkillWizard(props: {
  /** Nomes já usados — a checagem de duplicidade acontece no campo, não na publicação. */
  existentes: string[];
  onConcluido: () => void;
  onCancelar: () => void;
}) {
  const t = useTranslations("skillWizard");
  const tf = useTranslations("formflow");
  const tc = useTranslations("common");
  const m = useManifest("skill");

  if (m.estado === "ok") return <SkillForm {...props} manifest={m.manifest} />;

  return (
    <section className="card stack-sm">
      <header className="between">
        <h3 className="section-title">{t("title")}</h3>
        <button type="button" className="btn" onClick={props.onCancelar}>
          {tc("cancel")}
        </button>
      </header>
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

function SkillForm({
  existentes,
  onConcluido,
  onCancelar,
  manifest,
}: {
  existentes: string[];
  onConcluido: () => void;
  onCancelar: () => void;
  manifest: FormFlowManifest;
}) {
  const t = useTranslations("skillWizard");
  const tf = useTranslations("formflow");
  const tc = useTranslations("common");

  const { estado, set, regraDoCampo, aplicarProposta, anexar, desanexar, catalogos } = useFormFlow(
    manifest,
    { taken: existentes },
  );

  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  /** O resultado do plano. Guardado para que a RETENTATIVA não repita o que já deu certo — sem
   *  isto, a segunda tentativa recria a skill e recebe "já existe". */
  const [plano, setPlano] = useState<ResultadoPlano | null>(null);

  const texto = (id: string) => String(estado.valores[id] ?? "").trim();

  /** O documento da skill — instruções inline mais a procedência. */
  const documento = () => {
    const doc: Record<string, unknown> = {
      instructions: texto("instructions"),
      description: texto("description"),
    };
    // A procedência viaja com o recurso publicado (ADR-023), no vocabulário do OKF v0.2 e
    // SERIALIZADA — o Foundry exige metadata em string.
    const provenance = serializeProvenance(estado.origens);
    if (provenance) doc.metadata = { provenance };
    return doc;
  };

  /** Executa UMA operação do plano. É aqui que mora o que é específico da skill. */
  const executar = async (op: Operacao): Promise<string | null> => {
    const alvo = resolverPath(op, estado.valores);
    try {
      if (op.encoding === "multipart") {
        const form = new FormData();
        // O GRUPO VIRA PASTA: o serviço aceita upload de diretório e preserva o caminho, e é por
        // isso que `scripts` e `references` são campos separados no manifesto em vez de uma pilha
        // plana — a skill fica legível para quem for mantê-la depois.
        for (const grupo of ["scripts", "references"]) {
          for (const a of estado.anexos[grupo] ?? []) {
            form.append("files", new Blob([a.conteudo]), `${grupo}/${a.nome}`);
          }
        }
        // Nada anexado: a operação não tem o que fazer, e chamar o serviço com um form vazio seria
        // pedir a ele que decidisse o que isso significa.
        if (!form.has("files")) return null;
        const r = await authedFetch(alvo, { method: "POST", body: form });
        const b = await r.json().catch(() => ({}));
        return r.ok ? null : (b?.error ?? `HTTP ${r.status}`);
      }
      const r = await authedFetch(alvo, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: documento(), default: true }),
      });
      const b = await r.json().catch(() => ({}));
      return r.ok ? null : (b?.error ?? `HTTP ${r.status}`);
    } catch {
      return tc("backendUnreachable");
    }
  };

  const publicar = async () => {
    setBusy(true);
    setErro(null);
    const r = await executarPlano(manifest.plan ?? [], estado.valores, executar, {
      feitas: plano?.feitas ?? [],
    });
    setPlano(r);
    setBusy(false);

    const falhou = r.operacoes.find((o) => o.status === "falhou");
    if (!falhou) return onConcluido();

    // FALHA PARCIAL: as duas coisas são ditas. "A skill foi criada E o bundle falhou" evita que a
    // pessoa tente criar de novo — e o `plano` guardado faz a retentativa começar de onde parou.
    setErro(
      r.parcial
        ? t("erroParcial", { feitas: r.feitas.join(", "), motivo: falhou.erro ?? "" })
        : (falhou.erro ?? ""),
    );
    if (r.parcial) onConcluido();
  };

  const bloqueio = estado.bloqueio;
  const obrigatorias = estado.secoes.filter((s) => !s.opcional);

  return (
    <section className="card wizard">
      <FormFlowProposalTool
        manifest={manifest}
        valores={estado.valores}
        regraDoCampo={regraDoCampo}
        onAccept={aplicarProposta}
      />

      <header className="between wizard-head">
        <h3 className="section-title">{t("title")}</h3>
        <div className="row-tight">
          <button type="button" className="btn" disabled={busy} onClick={onCancelar}>
            {tc("cancel")}
          </button>
          <button
            type="button"
            className="btn btn-solid"
            disabled={busy || bloqueio !== null}
            title={bloqueio ?? undefined}
            onClick={() => void publicar()}
          >
            {busy ? t("publishing") : plano?.parcial ? t("retomar") : t("publish")}
          </button>
        </div>
      </header>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}
      {bloqueio && !busy && <p className="t-xs muted-line wizard-blocked">{bloqueio}</p>}

      <div className="wizard-body">
        <nav className="wizard-rail" aria-label={t("stepsLabel")}>
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

          {/* O PLANO, visível ANTES de publicar. Ele diz que são duas operações e que a segunda
              depende da primeira — que é a informação de que a pessoa precisa se a segunda
              falhar. Depois de rodar, cada linha carrega o desfecho. */}
          <PlanoRail manifest={manifest} plano={plano} />
        </nav>

        <div className="wizard-form">
          <FormFlowFields
            manifest={manifest}
            valores={estado.valores}
            set={set}
            regraDoCampo={regraDoCampo}
            catalogos={catalogos}
            busy={busy}
            origens={estado.origens}
            onAnexar={anexar}
            onDesanexar={desanexar}
            onRecusar={setErro}
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
            <details className="wizard-doc">
              <summary className="t-xs">{tf("verDocumento")}</summary>
              <pre className="doc-preview">{JSON.stringify(documento(), null, 2)}</pre>
            </details>
          </section>
        </div>
      </div>
    </section>
  );
}

/** O plano de publicação no rail: quantas operações, e o desfecho de cada uma depois de rodar. */
export function PlanoRail({
  manifest,
  plano,
}: {
  manifest: FormFlowManifest;
  plano: ResultadoPlano | null;
}) {
  const tf = useTranslations("formflow");
  const ops = manifest.plan ?? [];
  if (!ops.length) return null;
  const statusDe = (id: string) => plano?.operacoes.find((o) => o.id === id)?.status ?? "pendente";
  return (
    <div className="wizard-prov">
      <p className="t-2xs muted-line">{tf("plano")}</p>
      <ol className="plan-list">
        {ops.map((op) => {
          const s = statusDe(op.id);
          return (
            <li key={op.id} className={`plan-item plan-${s}`}>
              <span className="plan-dot" aria-hidden />
              <span className="t-2xs plan-title">{op.title ?? op.id}</span>
              <span className="t-2xs muted-line">{tf(`plan_${s}`)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
