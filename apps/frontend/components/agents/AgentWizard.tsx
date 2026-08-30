"use client";

// Wizard de agente — agora sobre o motor de FormFlow.
//
// O QUE SAIU DAQUI. Os campos, os rótulos, as regras, o texto da revisão e o plano de publicação
// eram código neste arquivo. Viraram um documento: `apps/backend/agents/assured/flows/agent.md`,
// `type: formflow` num bundle OKF. Trocar aquele documento troca este wizard inteiro — inclusive
// quais campos o agente pode escrever.
//
// O QUE FICOU, e é o motivo de este arquivo ainda existir: montar o DOCUMENTO DO FOUNDRY a partir
// dos valores. Isso é específico do recurso e não cabe no manifesto — ele declara em `plan` que
// existe um `POST /api/foundry/agents/{name}`, e não sabe (nem deveria) que `knowledge_base` é um
// atalho que o backend expande, que `mcp` vira um tool com `require_approval: always`, ou que o
// Foundry exige `metadata` em string.
//
// Continua valendo o que foi medido no SDK e confirmado na documentação:
//   * base de conhecimento → AzureAISearchTool, direto em `tools` (atalho `knowledge_base`)
//   * toolbox (e as skills dentro dele) → o toolbox É um servidor MCP: um `mcp` tool com a URL
//   * MCP externo → o mesmo `mcp` tool, com a URL do servidor de terceiro
//   * code interpreter, web search → tools de primeira parte, só o `type`

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authedFetch } from "@/lib/auth/api";
import { FormFlowFields, FormFlowProposalTool, useFormFlow } from "@/components/formflow/FormFlow";
import { useManifest } from "@/lib/formflow/load";
import { serializeProvenance } from "@/lib/okf";
import type { FormFlowManifest, Valores } from "@/lib/formflow/types";

/** Valores que o wizard pode abrir preenchidos. Existe para o rascunho do propositor (ADR-022)
 *  entrar por AQUI, e não por um segundo caminho de publicação: a proposta preenche o formulário,
 *  e quem publica continua sendo esta tela, com o papel Admin. */
export type AgentSeed = {
  nome?: string;
  descricao?: string;
  instrucoes?: string;
  kb?: string;
};

/** A semente, no vocabulário do manifesto. É a única tradução de nomes que sobrou, e ela existe
 *  porque `AgentSeed` é o contrato do propositor: mudar o nome dos campos dele seria mudar uma
 *  API por causa de um detalhe de tela. */
function sementeDe(s: AgentSeed | undefined): Valores {
  if (!s) return {};
  const v: Valores = {};
  if (s.nome) v.name = s.nome;
  if (s.descricao) v.description = s.descricao;
  if (s.instrucoes) v.instructions = s.instrucoes;
  if (s.kb) v.knowledge_base = s.kb;
  return v;
}

/** O WRAPPER: resolve o manifesto, e só monta o formulário quando ele existe.
 *
 *  A separação não é cosmética. O miolo semeia o estado no INICIALIZADOR do `useState` (ver
 *  `useFormFlow`), e um inicializador só roda uma vez — se ele montasse com `manifest = null` e
 *  recebesse o documento depois, as sementes nunca entrariam. Montar o miolo só com o manifesto
 *  em mãos é o que torna o inicializador correto, e de quebra elimina o quadro em que o
 *  formulário aparece vazio antes de o efeito rodar.
 *
 *  NÃO HÁ CÓPIA EMBUTIDA de reserva. Ela pareceria robustez e seria uma segunda fonte do mesmo
 *  formulário: no dia em que o documento mudasse, a tela renderizaria a cópia antiga sem erro
 *  nenhum. Os três motivos são distinguidos porque pedem ações diferentes — corrigir o nome,
 *  corrigir o documento, ou tentar de novo. */
export function AgentWizard(props: {
  existentes: string[];
  onCancelar: () => void;
  inicial?: AgentSeed;
}) {
  const t = useTranslations("agentWizard");
  const tf = useTranslations("formflow");
  const tc = useTranslations("common");
  const m = useManifest("agent");

  if (m.estado === "ok") return <AgentForm {...props} manifest={m.manifest} />;

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

function AgentForm({
  existentes,
  onCancelar,
  inicial,
  manifest,
}: {
  existentes: string[];
  onCancelar: () => void;
  inicial?: AgentSeed;
  manifest: FormFlowManifest;
}) {
  const t = useTranslations("agentWizard");
  const tf = useTranslations("formflow");
  const tc = useTranslations("common");
  const router = useRouter();

  const { estado, set, regraDoCampo, aplicarProposta, catalogos } = useFormFlow(manifest, {
    taken: existentes,
    inicial: sementeDe(inicial),
  });

  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // ── o documento do Foundry, a partir dos valores ────────────────────────────────────────
  const texto = (id: string) => String(estado.valores[id] ?? "").trim();
  const marcados = (id: string) => (estado.valores[id] as string[] | undefined) ?? [];

  /** As tools declaradas diretamente (os atalhos são expandidos pelo backend). */
  const tools = () => {
    const out: Record<string, unknown>[] = [];
    for (const tipo of marcados("tools")) out.push({ type: tipo });
    // O campo `pair` guarda os dois pedaços juntos porque um MCP com rótulo e sem URL não é
    // alcançável — meio preenchido é meio de nada.
    const [rotulo = "", url = ""] = texto("mcp").split("\t");
    if (rotulo.trim() && url.trim()) {
      out.push({
        type: "mcp",
        server_label: rotulo.trim().replace(/-/g, "_"),
        server_url: url.trim(),
        // Default seguro. A documentação avisa que o endpoint NÃO bloqueia a chamada — quem
        // precisa honrar isto é o runtime do agente. Nasce em "always" mesmo assim.
        require_approval: "always",
      });
    }
    return out;
  };

  const documento = () => {
    const doc: Record<string, unknown> = {
      kind: "prompt",
      model: texto("model"),
      instructions: texto("instructions"),
    };
    if (texto("knowledge_base")) doc.knowledge_base = texto("knowledge_base");
    // A procedência entra no METADATA da versão, no vocabulário do OKF v0.2 (lib/okf.ts), e
    // SERIALIZADA — o Foundry exige que valores de `metadata` sejam string.
    const provenance = serializeProvenance(estado.origens);
    if (provenance) doc.metadata = { provenance };
    if (texto("toolbox")) doc.toolbox = texto("toolbox");
    const ts = tools();
    if (ts.length) doc.tools = ts;
    return doc;
  };

  const publicar = async () => {
    setBusy(true);
    setErro(null);
    try {
      const alvo = `/api/foundry/agents/${encodeURIComponent(texto("name"))}`;
      const r = await authedFetch(alvo, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ definition: documento(), description: texto("description") }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      router.push(`/agents/${encodeURIComponent(body.name ?? texto("name"))}`);
    } catch {
      setErro(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  const bloqueio = estado.bloqueio;
  const obrigatorias = estado.secoes.filter((s) => !s.opcional);

  return (
    <section className="card wizard">
      {/* A tool que o agente do dock chama. Os campos oferecidos são os que o manifesto declara
          com `ai: true` — não uma lista escrita aqui. */}
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
          {/* A ação final fica SEMPRE VISÍVEL, e desabilitada com o motivo. */}
          <button
            type="button"
            className="btn btn-solid"
            disabled={busy || bloqueio !== null}
            title={bloqueio ?? undefined}
            onClick={() => void publicar()}
          >
            {busy ? t("publishing") : t("publish")}
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
        {/* O rail: navegação, não indicador. Mostra o estado REAL de cada seção e leva a qualquer
            uma — inclusive de volta, que era o caminho que o stepper de quatro passos não tinha. */}
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
            <li>
              <a href="#w-review" className="wizard-rail-item optional">
                <span className="wizard-rail-mark" aria-hidden>
                  ·
                </span>
                <span className="wizard-rail-text">
                  <span className="wizard-rail-title">{tf("step4")}</span>
                  <span className="wizard-rail-note">{tf("resumoRevisao")}</span>
                </span>
              </a>
            </li>
          </ol>

          {/* A PROCEDÊNCIA no rail, não escondida na revisão: é ela que viaja para o metadata da
              versão publicada (OKF v0.2), e quem publica precisa vê-la ANTES de publicar. */}
          <div className="wizard-prov">
            <p className="t-2xs muted-line">{tf("procedencia")}</p>
            {Object.keys(estado.origens).length ? (
              <ul className="wizard-prov-list">
                {Object.entries(estado.origens).map(([campo, origem]) => (
                  <li key={campo}>
                    <code className="t-2xs">{campo}</code>
                    {/* Sem fonte é DITO, não omitido: "o agente escreveu do próprio conhecimento"
                        é uma afirmação diferente de "ninguém escreveu isto". */}
                    <span className="t-2xs muted-line">
                      {origem.sources.length ? origem.sources.join(", ") : tf("semFonte")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="t-2xs muted-line">{tf("procedenciaVazia")}</p>
            )}
          </div>
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
          />

          <section id="w-review" className="wizard-section">
            <h4 className="wizard-section-title">{tf("step4")}</h4>
            <p className="muted t-sm">{tf("reviewHelp")}</p>

            {/* A REVISÃO EM PROSA, derivada do bloco `review:` do manifesto. O documento cru
                continua na tela, numa aba — mudou qual dos dois vem primeiro. */}
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
              {texto("toolbox") && (
                <p className="muted t-xs">{t("toolboxResolved", { name: texto("toolbox") })}</p>
              )}
            </details>
          </section>
        </div>
      </div>
    </section>
  );
}
