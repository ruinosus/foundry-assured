"use client";

// Criar base de conhecimento — sobre o motor de FormFlow e o executor de plano.
//
// ESTA É A TELA QUE MOTIVOU `lockedUntil`. A ordem não é preferência de interface: a base precisa
// EXISTIR antes de receber conteúdo, porque o container onde os arquivos vão é derivado do nome
// dela. O manifesto declara `lockedUntil: create_base` na seção de alimentação, e a seção fica
// travada até aquela operação rodar — antes disto, a regra existia como um `disabled={!created}`
// repetido em seis controles, e bastava esquecer um para o produto oferecer um caminho que falha.
//
// E ELA DECLARA `provenance: null`. O contrato de criação da base não tem `metadata`, então a
// procedência do que o agente escreveu NÃO viaja com o recurso. O manifesto diz isso, e a tela
// mostra — em vez de fingir que viaja, que é o que acontecia quando a ausência era silêncio.
//
// O caminho de repositório é o único não-Microsoft do produto: ele lê os arquivos e escreve no
// blob; do blob em diante o pipeline oficial retoma.

import { useTranslations } from "next-intl";
import { useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { FormFlowFields, FormFlowProposalTool, useFormFlow } from "@/components/formflow/FormFlow";
import { PlanoRail } from "@/components/skills/SkillWizard";
import { useManifest } from "@/lib/formflow/load";
import { executarPlano, pendentes, resolverPath, type ResultadoPlano } from "@/lib/formflow/plan";
import type { FormFlowManifest, Operacao } from "@/lib/formflow/types";

export function CreateKnowledge({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("knowledgeCreate");
  const tf = useTranslations("formflow");
  const m = useManifest("knowledge");

  if (m.estado === "ok") return <KnowledgeForm onCreated={onCreated} manifest={m.manifest} />;

  return (
    <section className="card stack-sm">
      <h3 className="section-title">{t("title")}</h3>
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

function KnowledgeForm({
  onCreated,
  manifest,
}: {
  onCreated: () => void;
  manifest: FormFlowManifest;
}) {
  const t = useTranslations("knowledgeCreate");
  const tf = useTranslations("formflow");
  const tc = useTranslations("common");

  const { estado, set, regraDoCampo, aplicarProposta, anexar, desanexar, catalogos } =
    useFormFlow(manifest);

  const [busy, setBusy] = useState(false);
  const [resultado, setResultado] = useState<{ tipo: "ok" | "bad"; texto: string } | null>(null);
  const [plano, setPlano] = useState<ResultadoPlano | null>(null);

  const texto = (id: string) => String(estado.valores[id] ?? "").trim();
  const feitas = plano?.feitas ?? [];
  /** O que a seção travada consulta: enquanto `create_base` estiver aqui, `feed` fica fechada. */
  const travadas = pendentes(manifest.plan ?? [], feitas);

  /** Qual caminho de alimentação a pessoa escolheu. O manifesto DECLARA os dois (`upload_files` e
   *  `import_repo`); declarar não é executar — ela usa um. */
  const caminho = (): string[] => {
    const ops = ["create_base"];
    if ((estado.anexos.files ?? []).length) ops.push("upload_files");
    else if (texto("repo")) ops.push("import_repo");
    return ops;
  };

  const executar = async (op: Operacao): Promise<string | null> => {
    const alvo = resolverPath(op, estado.valores) || "/api/foundry/knowledge";
    try {
      if (op.id === "create_base") {
        const r = await authedFetch("/api/foundry/knowledge", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: texto("name"), description: texto("description") }),
        });
        const b = await r.json().catch(() => ({}));
        if (!r.ok) return b?.error ?? `HTTP ${r.status}`;
        setResultado({ tipo: "ok", texto: t("created", { name: b.name ?? texto("name") }) });
        return null;
      }
      if (op.id === "upload_files") {
        const form = new FormData();
        for (const a of estado.anexos.files ?? []) {
          form.append("files", new Blob([a.conteudo]), a.nome);
        }
        const r = await authedFetch(alvo, { method: "POST", body: form });
        const b = await r.json().catch(() => ({}));
        return r.ok ? null : (b?.error ?? `HTTP ${r.status}`);
      }
      // import_repo
      const r = await authedFetch(alvo, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo: texto("repo"),
          token: texto("token"),
          ref: texto("ref"),
          subdir: texto("subdir"),
        }),
      });
      const b = await r.json().catch(() => ({}));
      // O TOKEN SAI DO ESTADO assim que a chamada termina — `retain: false` no manifesto. Não há
      // razão para ele continuar em memória depois de usado, e há razão para não continuar.
      set("token", "");
      if (!r.ok) return b?.error ?? `HTTP ${r.status}`;
      const partes = [t("imported", { count: b.ingested, repo: b.repo })];
      if (b.skipped_count > 0) partes.push(t("skipped", { count: b.skipped_count }));
      if (b.tree_truncated_by_github) partes.push(t("treeTruncated"));
      setResultado({ tipo: "ok", texto: partes.join(" ") });
      return null;
    } catch {
      return tc("backendUnreachable");
    }
  };

  const publicar = async () => {
    setBusy(true);
    setResultado(null);
    const r = await executarPlano(manifest.plan ?? [], estado.valores, executar, {
      selecionadas: caminho(),
      feitas,
    });
    setPlano(r);
    setBusy(false);

    const falhou = r.operacoes.find((o) => o.status === "falhou");
    if (!falhou) return onCreated();
    setResultado({
      tipo: "bad",
      texto: r.parcial
        ? t("erroParcial", { feitas: r.feitas.join(", "), motivo: falhou.erro ?? "" })
        : (falhou.erro ?? ""),
    });
    if (r.parcial) onCreated();
  };

  const bloqueio = estado.bloqueio;

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
        <button
          type="button"
          className="btn btn-solid"
          disabled={busy || bloqueio !== null}
          title={bloqueio ?? undefined}
          onClick={() => void publicar()}
        >
          {busy ? tc("loading") : feitas.length ? tf("plano_continuar") : t("createBtn")}
        </button>
      </header>

      {resultado && (
        <div className={`notice ${resultado.tipo === "bad" ? "notice-block" : ""}`}>
          <p className="notice-body">{resultado.texto}</p>
        </div>
      )}
      {bloqueio && !busy && <p className="t-xs muted-line wizard-blocked">{bloqueio}</p>}

      <div className="wizard-body">
        <nav className="wizard-rail" aria-label={tf("stepsLabel")}>
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

          {/* A PROCEDÊNCIA NÃO VIAJA, e o manifesto diz por quê. Antes, a ausência era silêncio —
              e silêncio, num campo de auditoria, é indistinguível de "viajou". */}
          {manifest.provenance === null && manifest.provenanceNote && (
            <div className="wizard-prov">
              <p className="t-2xs muted-line">{tf("procedencia")}</p>
              <p className="t-2xs muted-line">{manifest.provenanceNote}</p>
            </div>
          )}

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
            travadas={travadas}
            onAnexar={anexar}
            onDesanexar={desanexar}
            onRecusar={(msg) => setResultado({ tipo: "bad", texto: msg })}
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
          </section>
        </div>
      </div>
    </section>
  );
}
