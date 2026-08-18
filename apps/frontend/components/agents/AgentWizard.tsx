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
import { AiField } from "@/components/shell/AiField";
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

  const [passo, setPasso] = useState<1 | 2 | 3 | 4>(1);
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
  const [origens, setOrigens] = useState<Record<string, string[]>>({});
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

  const problemaNome = useCallback((): string | null => {
    const n = nome.trim();
    if (!n) return t("erroNomeVazio");
    if (!NOME_RECURSO.test(n)) return t("erroNomeFormato");
    if (n.length > 63) return t("erroNomeLongo");
    // Nome existente não é erro de digitação: é outra operação (publica versão do agente que já
    // existe). Dizer isso na etapa 1 evita a surpresa na etapa 4.
    if (existentes.includes(n)) return t("erroNomeExiste", { name: n });
    return null;
  }, [nome, existentes, t]);

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
    // A procedência entra no METADATA da versão. Só os campos que o agente escreveu aparecem —
    // o que a pessoa digitou sozinha não tem origem a declarar, e inventar uma seria pior que
    // não ter.
    const comOrigem = Object.entries(origens).filter(([, fontes]) => fontes.length);
    if (comOrigem.length) {
      // SERIALIZADA. O Foundry exige que valores de `metadata` sejam STRING — um objeto aqui é
      // recusado com "The JSON value could not be converted to System.String", medido publicando.
      doc.metadata = {
        ...(doc.metadata as Record<string, unknown> | undefined),
        provenance: JSON.stringify(Object.fromEntries(comOrigem)),
      };
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

  /** O que FALTA para avançar, ou null. Devolve o motivo em vez de um booleano porque um botão
   *  desabilitado sem explicação é um beco: a pessoa vê que não dá e não sabe o que fazer. A
   *  regra é "opcional nunca trava" — então, quando algo trava, é obrigatório, e dizer qual é o
   *  mínimo. */
  const faltaPara = (): string | null => {
    if (passo === 1) return problemaNome();
    if (passo === 2) {
      if (!instrucoes.trim()) return t("faltaInstrucoes");
      if (!modelo.trim()) return t("faltaModelo");
    }
    // Etapa 3 é toda OPCIONAL — base, toolbox e MCP. Ela nunca trava, por regra.
    return null;
  };
  const bloqueio = faltaPara();
  const podeAvancar = bloqueio === null;

  /** Aplica a proposta aceita: o valor vai para o campo, a fonte vai para a procedência. Os dois
   *  juntos, sempre — um valor sem origem registrada é exatamente o que a auditoria não aceita. */
  const aplicar = (p: FieldProposal) => {
    if (p.field === "instructions") setInstrucoes(p.value);
    else if (p.field === "description") setDescricao(p.value);
    else if (p.field === "name") setNome(p.value);
    setOrigens((o) => ({ ...o, [p.field]: p.sources }));
  };

  return (
    <section className="card stack-sm">
      {/* A tool que o agente do dock chama para propor um campo. Registrada AQUI, dentro do
          wizard, porque é o formulário que sabe quais campos existem e como aplicá-los — e
          porque ela deixa de existir quando o formulário fecha, que é o comportamento certo:
          uma tool de proposta viva sem formulário aberto proporia para o nada. */}
      <FieldProposalTool onAccept={aplicar} resource="agent" fields={["name", "description", "instructions"]} />
      <header className="between">
        <h3 className="section-title">{t("title")}</h3>
        <button type="button" className="btn" disabled={busy} onClick={onCancelar}>
          {tc("cancel")}
        </button>
      </header>

      <ol className="steps" aria-label={t("stepsLabel")}>
        {([1, 2, 3, 4] as const).map((p) => (
          <li key={p} className={`step ${passo === p ? "on" : passo > p ? "done" : ""}`}>
            <span className="step-num">{p}</span>
            <span className="step-label">{t(`step${p}`)}</span>
          </li>
        ))}
      </ol>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}

      {passo === 1 && (
        <div className="stack-sm">
          <input
            className="acct-btn"
            placeholder={t("namePlaceholder")}
            value={nome}
            disabled={busy}
            onChange={(e) => setNome(e.target.value)}
          />
          {nome.trim() && problemaNome() && <p className="t-xs bad-line">{problemaNome()}</p>}
          <p className="muted t-xs">{t("nameHelp")}</p>
          <input
            className="acct-btn"
            placeholder={t("descriptionPlaceholder")}
            value={descricao}
            disabled={busy}
            onChange={(e) => setDescricao(e.target.value)}
          />
        </div>
      )}

      {passo === 2 && (
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
          {/* Nome de deployment do modelo: não se traduz, é o que a pessoa vê no portal. */}
          <label className="muted t-xs">{t("modelLabel")}</label>
          <input
            className="acct-btn"
            value={modelo}
            disabled={busy}
            onChange={(e) => setModelo(e.target.value)}
          />
        </div>
      )}

      {passo === 3 && catalogoErro && (
        <div className="notice notice-block">
          <p className="notice-body">{t("catalogoIndisponivel", { what: catalogoErro })}</p>
        </div>
      )}

      {passo === 3 && (
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
              >
                <option value="">{t("toolboxNone")}</option>
                {toolboxes.map((x) => (
                  <option key={x.name} value={x.name}>
                    {x.name}
                  </option>
                ))}
              </select>
            )}
            {/* A ressalva honesta: skills dentro do toolbox chegam como MCP Resources, e não foi
                verificado se o agente server-side as lê. Dizer isso é melhor que prometer. */}
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
      )}

      {passo === 4 && (
        <div className="stack-sm">
          <p className="muted t-sm">{t("reviewHelp")}</p>
          <pre className="doc-preview">{JSON.stringify(documento(), null, 2)}</pre>
          {toolbox && <p className="muted t-xs">{t("toolboxResolved", { name: toolbox })}</p>}
        </div>
      )}

      <div className="row">
        {passo > 1 && (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => setPasso((p) => (p - 1) as 1 | 2 | 3)}
          >
            {t("back")}
          </button>
        )}
        <div className="grow" />
        {passo < 4 ? (
          <button
            type="button"
            className="btn btn-solid"
            disabled={busy || !podeAvancar}
            title={bloqueio ?? undefined}
            onClick={() => setPasso((p) => (p + 1) as 2 | 3 | 4)}
          >
            {t("next")}
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-solid"
            disabled={busy}
            onClick={() => void publicar()}
          >
            {busy ? t("publishing") : t("publish")}
          </button>
        )}
      </div>
    </section>
  );
}
