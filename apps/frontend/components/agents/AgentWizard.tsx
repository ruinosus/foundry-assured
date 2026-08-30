"use client";

// Wizard de agente — quatro etapas, substituindo o campo que pedia JSON cru.
//
// A ETAPA 3 É A RAZÃO DE ELE EXISTIR. "Adicionar uma capacidade" era, até aqui, escrever à mão
// um objeto como
//
//     {"type":"azure_ai_search","azure_ai_search":{"indexes":[{"index_name":"…"}]}}
//
// Quem sabe escrever isso não precisa deste produto. Agora a etapa lê o catálogo REAL — as bases
// que existem, os toolboxes que existem — e a pessoa escolhe da lista. O documento sai montado.
//
// O que cada capacidade exige foi medido no SDK e confirmado na documentação:
//   * base de conhecimento → AzureAISearchTool, direto em `tools` (atalho `knowledge_base`)
//   * toolbox (e as skills dentro dele) → o toolbox É um servidor MCP: um `mcp` tool com a URL
//   * MCP externo → o mesmo `mcp` tool, com a URL do servidor de terceiro
//   * code interpreter, web search → tools de primeira parte, só o `type`

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authedFetch } from "@/lib/auth/api";
import { AiField, AGENTE_DO_FORMULARIO } from "@/components/shell/AiField";
import { serializeProvenance, type FieldOrigin } from "@/lib/okf";
import { FieldProposalTool, type FieldProposal } from "@/components/shell/FieldProposal";

const NOME_RECURSO = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** Tools de primeira parte cujo ÚNICO campo obrigatório é `type`.
 *
 * A lista foi verificada no SDK, não escolhida: cada uma tem `:ivar type: … Required.` e nenhum
 * outro campo obrigatório. Oferecer aqui uma que precise de configuração (bing_grounding exige
 * `bing_grounding`, file_search exige vector store, mcp exige URL) produziria um agente que falha
 * na primeira chamada — o pior tipo de erro, porque acontece longe de onde foi causado. */
const TOOLS_SIMPLES = ["code_interpreter", "web_search", "image_generation"] as const;

type Base = { name: string };
type Toolbox = { name: string; default_version: string | null };

/** Valores que o wizard pode abrir preenchidos. Existe para o rascunho do propositor (ADR-022)
 *  entrar por AQUI, e não por um segundo caminho de publicação: a proposta preenche o formulário,
 *  e quem publica continua sendo esta tela, com o papel Admin. */
export type AgentSeed = {
  nome?: string;
  descricao?: string;
  instrucoes?: string;
  kb?: string;
};

export function AgentWizard({
  existentes,
  onCancelar,
  inicial,
}: {
  existentes: string[];
  onCancelar: () => void;
  inicial?: AgentSeed;
}) {
  const t = useTranslations("agentWizard");
  const tc = useTranslations("common");
  const router = useRouter();

  // O rascunho entra como VALOR INICIAL de campo editável, nunca como algo já gravado: o estado
  // continua sendo do formulário, e cada campo pode ser mudado antes de publicar.
  const [nome, setNome] = useState(inicial?.nome ?? "");
  const [descricao, setDescricao] = useState(inicial?.descricao ?? "");
  const [instrucoes, setInstrucoes] = useState(inicial?.instrucoes ?? "");
  const [modelo, setModelo] = useState("gpt-5-mini");

  const [kb, setKb] = useState(inicial?.kb ?? "");
  const [toolbox, setToolbox] = useState("");
  const [simples, setSimples] = useState<Set<string>>(new Set());
  const [mcpLabel, setMcpLabel] = useState("");
  const [mcpUrl, setMcpUrl] = useState("");

  const [bases, setBases] = useState<Base[]>([]);
  const [toolboxes, setToolboxes] = useState<Toolbox[]>([]);
  const [busy, setBusy] = useState(false);
  // A PROCEDÊNCIA de cada campo escrito pelo agente (ADR-023). Ela viaja para o `metadata` da
  // versão publicada: a partir daí, "de onde veio esta instrução" tem resposta no Foundry, com
  // versão e histórico — e não só na memória de quem estava na tela naquele dia.
  const [origens, setOrigens] = useState<Record<string, FieldOrigin>>({});
  const [erro, setErro] = useState<string | null>(null);
  //: O que NÃO pôde ser listado — distingue "não há" de "não consegui ler".
  const [catalogoErro, setCatalogoErro] = useState<string | null>(null);

  // O catálogo real é carregado assim que o wizard abre: a etapa 3 oferece o que EXISTE.
  //
  // LISTA VAZIA E FALHA DE LEITURA NÃO PODEM PARECER A MESMA COISA. O `catch` que devolvia `{}`
  // fazia as duas produzirem um select em branco — e "ainda não criei base nenhuma" leva a pessoa
  // a criar uma, enquanto "não consegui ler as bases" leva a tentar de novo. Um select vazio
  // calado faz alguém publicar um agente sem base achando que não havia nenhuma.
  useEffect(() => {
    const ler = async (url: string, chave: "bases" | "toolboxes") => {
      const r = await authedFetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const b = await r.json();
      return (b?.[chave] ?? []) as never[];
    };
    void (async () => {
      const [k, tb] = await Promise.allSettled([
        ler("/api/foundry/knowledge", "bases"),
        ler("/api/foundry/toolboxes", "toolboxes"),
      ]);
      if (k.status === "fulfilled") setBases(k.value);
      if (tb.status === "fulfilled") setToolboxes(tb.value);
      // Uma falha PARCIAL também é dita: sem base o agente ainda publica, mas quem escolheu
      // "sem base" precisa saber se escolheu ou se a lista não carregou.
      const falhou = [k.status === "rejected" && "knowledge", tb.status === "rejected" && "toolboxes"]
        .filter(Boolean)
        .join(", ");
      setCatalogoErro(falhou || null);
    })();
  }, []);

  /** A regra do nome, aplicada a QUALQUER valor. Parametrizada porque a mesma regra precisa valer
   *  em dois lugares — o campo e a proposta do agente — e duas cópias divergem. */
  const problemaNomeDe = useCallback(
    (valor: string): string | null => {
      const n = valor.trim();
      if (!n) return t("erroNomeVazio");
      if (!NOME_RECURSO.test(n)) return t("erroNomeFormato");
      if (n.length > 63) return t("erroNomeLongo");
      // Nome existente não é erro de digitação: é outra operação (publica versão do agente que já
      // existe). Dizer isso na etapa 1 evita a surpresa na etapa 4.
      if (existentes.includes(n)) return t("erroNomeExiste", { name: n });
      return null;
    },
    [existentes, t],
  );

  const problemaNome = useCallback(() => problemaNomeDe(nome), [problemaNomeDe, nome]);

  /** A regra de CADA campo que o agente pode propor. É esta função que o card de proposta usa —
   *  a mesma, não uma cópia. Antes disto, um `name` com maiúsculas passava no card e só reprovava
   *  na publicação, três telas depois de ter sido escrito. */
  const regraDoCampo = useCallback(
    (campo: string, valor: string): string | null => {
      if (campo === "name") return problemaNomeDe(valor);
      if (campo === "instructions" && !valor.trim()) return t("faltaInstrucoes");
      return null;
    },
    [problemaNomeDe, t],
  );

  /** As tools declaradas diretamente (os atalhos são expandidos pelo backend). */
  const tools = () => {
    const out: Record<string, unknown>[] = [];
    for (const tipo of simples) out.push({ type: tipo });
    if (mcpUrl.trim() && mcpLabel.trim()) {
      out.push({
        type: "mcp",
        server_label: mcpLabel.trim().replace(/-/g, "_"),
        server_url: mcpUrl.trim(),
        // Default seguro. A documentação avisa que o endpoint NÃO bloqueia a chamada — quem
        // precisa honrar isto é o runtime do agente. Nasce em "always" mesmo assim.
        require_approval: "always",
      });
    }
    return out;
  };

  /** O documento exato, como vai ser enviado. */
  const documento = () => {
    const doc: Record<string, unknown> = {
      kind: "prompt",
      model: modelo.trim(),
      instructions: instrucoes.trim(),
    };
    if (kb) doc.knowledge_base = kb;
    // A procedência entra no METADATA da versão, no vocabulário do OKF v0.2 (lib/okf.ts). Só os
    // campos que o agente escreveu aparecem — o que a pessoa digitou sozinha não tem origem a
    // declarar, e inventar uma seria pior que não ter.
    //
    // SERIALIZADA. O Foundry exige que valores de `metadata` sejam STRING — um objeto aqui é
    // recusado com "The JSON value could not be converted to System.String", medido publicando.
    const provenance = serializeProvenance(origens);
    if (provenance) {
      doc.metadata = { ...(doc.metadata as Record<string, unknown> | undefined), provenance };
    }
    // Atalhos: o backend expande os dois para o tool completo, porque montar a URL do toolbox
    // exigiria conhecer o endpoint do project — informação de quem opera, não de quem usa.
    if (toolbox) doc.toolbox = toolbox;
    const ts = tools();
    if (ts.length) doc.tools = ts;
    return doc;
  };

  const publicar = async () => {
    setBusy(true);
    setErro(null);
    try {
      const alvo = `/api/foundry/agents/${encodeURIComponent(nome.trim())}`;
      const r = await authedFetch(alvo, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ definition: documento(), description: descricao.trim() }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      router.push(`/agents/${encodeURIComponent(body.name ?? nome.trim())}`);
    } catch {
      setErro(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (tipo: string) =>
    setSimples((s) => {
      const n = new Set(s);
      n.has(tipo) ? n.delete(tipo) : n.add(tipo);
      return n;
    });

  /** O ESTADO REAL DE CADA SEÇÃO — e é ele que o rail mostra.
   *
   *  Antes, o stepper era um INDICADOR: numerava as quatro etapas e dizia em qual a pessoa
   *  estava, sem dizer o que faltava em cada uma nem deixar voltar clicando. Quem chegava na
   *  revisão e queria corrigir o nome tinha que percorrer o caminho de volta.
   *
   *  `pendencia` devolve o MOTIVO, nunca um booleano: um passo marcado como incompleto sem dizer
   *  o que falta é um beco. E "opcional nunca trava" continua valendo — capacidades tem
   *  `opcional: true` e nunca aparece como pendência. */
  const secoes = [
    {
      id: "identity" as const,
      titulo: t("step1"),
      pendencia: problemaNome(),
      resumo: nome.trim() || t("resumoSemNome"),
    },
    {
      id: "behavior" as const,
      titulo: t("step2"),
      pendencia: !instrucoes.trim()
        ? t("faltaInstrucoes")
        : !modelo.trim()
          ? t("faltaModelo")
          : null,
      resumo: instrucoes.trim() ? t("resumoInstrucoes", { model: modelo.trim() }) : t("resumoSemInstrucoes"),
    },
    {
      id: "capabilities" as const,
      titulo: t("step3"),
      pendencia: null,
      opcional: true,
      resumo: resumoCapacidades(),
    },
    {
      id: "review" as const,
      titulo: t("step4"),
      pendencia: null,
      resumo: t("resumoRevisao"),
    },
  ];

  /** O que impede de PUBLICAR — a primeira pendência de qualquer seção. É a mesma informação que
   *  o rail mostra por seção, aqui agregada para o botão. */
  const bloqueio = secoes.map((s) => s.pendencia).find((x) => x) ?? null;

  /** Quantas seções obrigatórias estão prontas. O rail mostra isto no topo. */
  const obrigatorias = secoes.filter((s) => !s.opcional);
  const prontas = obrigatorias.filter((s) => !s.pendencia).length;

  /** O que o agente VAI poder alcançar, em prosa. A mesma informação do documento — dita para
   *  quem publica, não para quem lê JSON. */
  function resumoAlcance(): string {
    const partes: string[] = [];
    if (kb) partes.push(t("alcanceBase", { name: kb }));
    for (const tipo of simples) partes.push(t(`tool_${tipo}` as never));
    if (toolbox) partes.push(t("alcanceToolbox", { name: toolbox }));
    if (mcpUrl.trim() && mcpLabel.trim()) partes.push(t("alcanceMcp", { label: mcpLabel.trim() }));
    return partes.length ? t("alcanceLista", { list: partes.join(", ") }) : t("alcanceNada");
  }

  function resumoCapacidades(): string {
    const partes: string[] = [];
    if (kb) partes.push(t("resumoBase", { name: kb }));
    if (toolbox) partes.push(t("resumoToolbox", { name: toolbox }));
    if (simples.size) partes.push(t("resumoTools", { count: simples.size }));
    if (mcpUrl.trim() && mcpLabel.trim()) partes.push(t("resumoMcp", { label: mcpLabel.trim() }));
    return partes.length ? partes.join(" · ") : t("resumoSemCapacidades");
  }

  /** Aplica a proposta aceita: o valor vai para o campo, a fonte vai para a procedência. Os dois
   *  juntos, sempre — um valor sem origem registrada é exatamente o que a auditoria não aceita. */
  const aplicar = (p: FieldProposal) => {
    if (p.field === "instructions") setInstrucoes(p.value);
    else if (p.field === "description") setDescricao(p.value);
    else if (p.field === "name") setNome(p.value);
    // A ORIGEM INTEIRA, não só as fontes: quem escreveu e quando entram junto, senão um campo
    // escrito pelo agente sem fonte ficaria indistinguível de um campo digitado à mão (lib/okf.ts).
    setOrigens((o) => ({
      ...o,
      [p.field]: {
        by: AGENTE_DO_FORMULARIO,
        at: new Date().toISOString(),
        sources: p.sources,
      },
    }));
  };

  return (
    <section className="card wizard">
      {/* A tool que o agente do dock chama para propor um campo. Registrada AQUI, dentro do
          wizard, porque é o formulário que sabe quais campos existem e como aplicá-los — e
          porque ela deixa de existir quando o formulário fecha, que é o comportamento certo:
          uma tool de proposta viva sem formulário aberto proporia para o nada. */}
      <FieldProposalTool
        onAccept={aplicar}
        resource="agent"
        fields={["name", "description", "instructions"]}
        // O que está no campo AGORA — é o lado esquerdo do diff no card.
        current={{ name: nome, description: descricao, instructions: instrucoes }}
        validate={regraDoCampo}
      />

      <header className="between wizard-head">
        <h3 className="section-title">{t("title")}</h3>
        <div className="row-tight">
          <button type="button" className="btn" disabled={busy} onClick={onCancelar}>
            {tc("cancel")}
          </button>
          {/* A AÇÃO FINAL FICA SEMPRE VISÍVEL, e desabilitada com o motivo. Ela era o botão do
              último passo: só aparecia depois de percorrer os quatro, e quem queria saber o que
              ainda faltava tinha que chegar lá para descobrir. */}
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
        {/* ── O RAIL ──────────────────────────────────────────────────────────────────────
            Navegação, não indicador. Ele mostra o estado REAL de cada seção (pronta, o que
            falta, opcional) e leva a qualquer uma — inclusive de volta, que era o caminho que
            o stepper de quatro passos não tinha. */}
        <nav className="wizard-rail" aria-label={t("stepsLabel")}>
          <p className="wizard-rail-head">
            <span className="t-2xs muted-line">{t("progresso")}</span>
            <span className="t-sm strong">{t("progressoContagem", { done: prontas, total: obrigatorias.length })}</span>
          </p>
          <ol className="wizard-rail-list">
            {secoes.map((sec, i) => (
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

          {/* A PROCEDÊNCIA, no rail e não escondida na revisão: ela é o que viaja para o
              `metadata` da versão publicada (ADR-023), e quem publica precisa vê-la antes de
              publicar, não depois. */}
          <div className="wizard-prov">
            <p className="t-2xs muted-line">{t("procedencia")}</p>
            {Object.keys(origens).length ? (
              <ul className="wizard-prov-list">
                {Object.entries(origens).map(([campo, origem]) => (
                  <li key={campo}>
                    <code className="t-2xs">{campo}</code>
                    {/* Sem fonte é DITO, não omitido: "o agente escreveu do próprio
                        conhecimento" é uma afirmação diferente de "ninguém escreveu isto". */}
                    <span className="t-2xs muted-line">
                      {origem.sources.length ? origem.sources.join(", ") : t("semFonte")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="t-2xs muted-line">{t("procedenciaVazia")}</p>
            )}
          </div>
        </nav>

        {/* ── O FORMULÁRIO ────────────────────────────────────────────────────────────────
            As quatro seções coexistem. Não há "avançar": a pessoa vê o formulário inteiro e o
            rail diz onde está o que falta. */}
        <div className="wizard-form">
          <section id="w-identity" className="wizard-section">
            <h4 className="wizard-section-title">{t("step1")}</h4>
            <div className="stack-sm">
              <AiField field="name" label={t("step1")} value={nome} resource={t("resourceAgent")}>
                <input
                  className="acct-btn"
                  placeholder={t("namePlaceholder")}
                  value={nome}
                  disabled={busy}
                  onChange={(e) => setNome(e.target.value)}
                />
              </AiField>
              {/* A VALIDAÇÃO APARECE NO CAMPO, enquanto se digita — não no clique em Avançar.
                  Só depois de a pessoa ter escrito algo: reclamar de campo vazio que ela ainda
                  não tocou é ruído. */}
              {nome.trim() && problemaNome() && <p className="t-xs bad-line">{problemaNome()}</p>}
              {nome.trim() && !problemaNome() && (
                <p className="t-xs ok-line">{t("nomeOk", { count: nome.trim().length })}</p>
              )}
              <p className="muted t-xs">{t("nameHelp")}</p>
              <AiField
                field="description"
                label={t("descriptionLabel")}
                value={descricao}
                resource={t("resourceAgent")}
              >
                <input
                  className="acct-btn"
                  placeholder={t("descriptionPlaceholder")}
                  value={descricao}
                  disabled={busy}
                  onChange={(e) => setDescricao(e.target.value)}
                />
              </AiField>
            </div>
          </section>

          <section id="w-behavior" className="wizard-section">
            <h4 className="wizard-section-title">{t("step2")}</h4>
            <div className="stack-sm">
              <p className="muted t-sm">{t("behaviorHelp")}</p>
              {/* O catálogo entra no contexto: sugerir instruções sabendo que existe uma base
                  chamada helpdesk-kb produz texto útil; sem isso, produz texto genérico. */}
              <AiField
                field="instructions"
                label={t("step2")}
                value={instrucoes}
                resource={t("resourceAgent")}
              >
                <textarea
                  className="acct-btn"
                  rows={9}
                  placeholder={t("instructionsPlaceholder")}
                  value={instrucoes}
                  disabled={busy}
                  onChange={(e) => setInstrucoes(e.target.value)}
                />
              </AiField>
              {/* Contagem + quem escreveu. "Escrito por você" vs "escrito pelo agente" é a mesma
                  informação que vai para o metadata — dita aqui, onde a decisão acontece. */}
              <p className="t-xs muted-line">
                {t("contagem", { count: instrucoes.length })}
                {instrucoes.trim() ? ` · ${t("minimoAtendido")}` : ""}
                {origens.instructions ? ` · ${t("escritoPeloAgente")}` : ` · ${t("escritoPorVoce")}`}
              </p>
              <label className="muted t-xs" htmlFor="w-model">
                {t("modelLabel")}
              </label>
              {/* Nome de deployment do modelo: não se traduz, é o que a pessoa vê no portal. */}
              <input
                id="w-model"
                className="acct-btn"
                value={modelo}
                disabled={busy}
                onChange={(e) => setModelo(e.target.value)}
              />
            </div>
          </section>

          <section id="w-capabilities" className="wizard-section">
            <h4 className="wizard-section-title">
              {t("step3")} <span className="t-2xs muted-line">{t("opcionalNuncaTrava")}</span>
            </h4>

            {catalogoErro && (
              <div className="notice notice-block">
                <p className="notice-body">{t("catalogoIndisponivel", { what: catalogoErro })}</p>
              </div>
            )}

            <div className="stack-sm">
              <p className="muted t-sm">{t("capabilitiesHelp")}</p>

              <div className="stack-sm">
                <p className="t-xs strong">{t("kbTitle")}</p>
                {bases.length === 0 ? (
                  <p className="muted t-xs">{t("kbEmpty")}</p>
                ) : (
                  <select
                    className="acct-btn"
                    value={kb}
                    disabled={busy}
                    onChange={(e) => setKb(e.target.value)}
                    aria-label={t("kbTitle")}
                  >
                    <option value="">{t("kbNone")}</option>
                    {bases.map((b) => (
                      <option key={b.name} value={b.name}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                )}
                <p className="muted t-xs">{t("kbHelp")}</p>
              </div>

              <div className="stack-sm">
                <p className="t-xs strong">{t("toolboxTitle")}</p>
                {toolboxes.length === 0 ? (
                  <p className="muted t-xs">{t("toolboxEmpty")}</p>
                ) : (
                  <select
                    className="acct-btn"
                    value={toolbox}
                    disabled={busy}
                    onChange={(e) => setToolbox(e.target.value)}
                    aria-label={t("toolboxTitle")}
                  >
                    <option value="">{t("toolboxNone")}</option>
                    {toolboxes.map((x) => (
                      <option key={x.name} value={x.name}>
                        {x.name}
                      </option>
                    ))}
                  </select>
                )}
                {/* A ressalva honesta: skills dentro do toolbox chegam como MCP Resources, e não
                    foi verificado se o agente server-side as lê. Dizer isso é melhor que
                    prometer. */}
                <p className="muted t-xs">{t("toolboxHelp")}</p>
              </div>

              <div className="stack-sm">
                <p className="t-xs strong">{t("toolsTitle")}</p>
                <div className="row-tight">
                  {TOOLS_SIMPLES.map((tipo) => (
                    <label key={tipo} className="row-tight t-sm">
                      <input
                        type="checkbox"
                        checked={simples.has(tipo)}
                        disabled={busy}
                        onChange={() => toggle(tipo)}
                      />
                      {t(`tool_${tipo}`)}
                    </label>
                  ))}
                </div>
              </div>

              <div className="stack-sm">
                <p className="t-xs strong">{t("mcpTitle")}</p>
                <div className="row-tight">
                  <input
                    className="acct-btn grow"
                    placeholder={t("mcpLabelPlaceholder")}
                    value={mcpLabel}
                    disabled={busy}
                    onChange={(e) => setMcpLabel(e.target.value)}
                  />
                  <input
                    className="acct-btn grow"
                    placeholder="https://…/mcp"
                    value={mcpUrl}
                    disabled={busy}
                    onChange={(e) => setMcpUrl(e.target.value)}
                  />
                </div>
                <p className="muted t-xs">{t("mcpHelp")}</p>
              </div>
            </div>
          </section>

          <section id="w-review" className="wizard-section">
            <h4 className="wizard-section-title">{t("step4")}</h4>
            <p className="muted t-sm">{t("reviewHelp")}</p>

            {/* A REVISÃO EM PROSA, antes do JSON. O documento cru é legível para quem escreve
                SDK; quem publica precisa saber o que o agente VAI e NÃO VAI poder fazer. As duas
                coisas continuam na tela — mudou qual delas vem primeiro. */}
            <dl className="review">
              <dt>{t("revisaoVaiCriar")}</dt>
              <dd>{t("revisaoVaiCriarTexto", { name: nome.trim() || "—" })}</dd>
              <dt>{t("revisaoVaiResponder")}</dt>
              <dd>
                {kb
                  ? t("revisaoComBase", { model: modelo.trim() || "—", kb })
                  : t("revisaoSemBase", { model: modelo.trim() || "—" })}
              </dd>
              <dt>{t("revisaoVaiPoder")}</dt>
              <dd>{resumoAlcance()}</dd>
              <dt>{t("revisaoNaoVaiPoder")}</dt>
              <dd>{t("revisaoNaoVaiPoderTexto")}</dd>
            </dl>

            <details className="wizard-doc">
              <summary className="t-xs">{t("verDocumento")}</summary>
              <pre className="doc-preview">{JSON.stringify(documento(), null, 2)}</pre>
              {toolbox && <p className="muted t-xs">{t("toolboxResolved", { name: toolbox })}</p>}
            </details>
          </section>
        </div>
      </div>
    </section>
  );
}
