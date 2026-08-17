// @gera-formato-externo — este arquivo emite YAML na linguagem do Microsoft Agent Framework.
// As palavras aqui (`kind: Workflow`, `InvokeAzureAgent`, `EndWorkflow`) são o CONTRATO dessa
// linguagem, não texto de interface: traduzi-las quebraria o arquivo gerado.
//
// Serializador do canvas — o único código nosso na cadeia do workflow.
//
// A MÁXIMA MAIOR permite isto e delimita: a linguagem, o interpretador, o HITL e o hosting são da
// Microsoft; o canvas e este serializador são nossos, porque o portal do Foundry só dá o designer
// a quem tem RBAC no Azure — e o designer dele é aposentado em 01/12/2026 e não aceita hosted
// agents. A lacuna é o editor; o formato não.
//
// A RESTRIÇÃO QUE DEFINE O DESENHO: a linguagem declarativa NÃO tem "nós e arestas". É uma lista
// aninhada de ações, com o grafo emergindo de `ConditionGroup` e `GotoAction`. Um DAG desenhado
// livremente não mapeia. Por isso o canvas é uma SEQUÊNCIA com ramificação explícita, e não uma
// tela onde se liga qualquer coisa a qualquer coisa: um editor que aceita desenhar o impossível e
// falha na publicação é pior que um que só deixa desenhar o que roda.

/** Um passo do canvas. É o que a pessoa manipula; o YAML é derivado. */
export type FlowStep =
  | { kind: "agent"; id: string; label: string; agent: string; output?: string }
  | { kind: "message"; id: string; label: string; text: string }
  | { kind: "approval"; id: string; label: string; prompt: string; variable: string }
  | { kind: "question"; id: string; label: string; text: string; variable: string };

export type Flow = { steps: FlowStep[] };

/** Identificador aceito pela linguagem: é a chave de `GotoAction`, então precisa ser estável. */
export function normalizeId(raw: string): string {
  const base = raw
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return base || "passo";
}

/** Escapa um texto para dentro de YAML sem depender de biblioteca.
 *
 * Bloco literal (`|-`) em vez de aspas: o texto de um passo é escrito por humanos e vai ter
 * dois-pontos, aspas e quebras de linha. Escapar tudo em linha produziria YAML frágil que quebra
 * na primeira mensagem com `:` — e o erro apareceria só na publicação.
 */
function literal(text: string, indent: number): string {
  const pad = " ".repeat(indent);
  const linhas = (text || "").split("\n").map((l) => `${pad}  ${l}`);
  return `|-\n${linhas.join("\n")}`;
}

/** O canvas vira YAML declarativo do Agent Framework. */
export function toYaml(flow: Flow, meta: { name: string; description?: string }): string {
  const linhas: string[] = [
    "# Fluxo gerado pelo canvas — linguagem declarativa do Microsoft Agent Framework.",
    "#",
    "# Editado visualmente, mas o formato é de primeira parte: o mesmo YAML roda pelo",
    "# WorkflowFactory, e continua legível e editável fora deste produto.",
    "kind: Workflow",
    "trigger:",
    "  kind: OnConversationStart",
    `  id: ${normalizeId(meta.name)}`,
    "  actions:",
  ];

  for (const s of flow.steps) {
    const id = normalizeId(s.id);
    linhas.push("");
    if (s.kind === "agent") {
      linhas.push(`    - kind: InvokeAzureAgent`);
      linhas.push(`      id: ${id}`);
      linhas.push(`      displayName: ${JSON.stringify(s.label)}`);
      linhas.push(`      agent:`);
      linhas.push(`        name: ${s.agent}`);
      linhas.push(`      output:`);
      // `autoSend: true` só no último passo de agente: cada passo que envia produz uma mensagem
      // na conversa, e um fluxo de três agentes com todos enviando responde três vezes.
      const ultimo = flow.steps.filter((x) => x.kind === "agent").at(-1) === s;
      linhas.push(`        autoSend: ${ultimo ? "true" : "false"}`);
      if (s.output) linhas.push(`        responseObject: Local.${normalizeId(s.output)}`);
    } else if (s.kind === "message") {
      linhas.push(`    - kind: SendActivity`);
      linhas.push(`      id: ${id}`);
      linhas.push(`      displayName: ${JSON.stringify(s.label)}`);
      linhas.push(`      activity:`);
      linhas.push(`        text: ${literal(s.text, 8)}`);
    } else if (s.kind === "approval") {
      // Pausa o fluxo de verdade: emite `request_info`, que é o mesmo mecanismo por trás do
      // approval card que o frontend já renderiza. Não há adaptador entre um e outro.
      linhas.push(`    - kind: RequestExternalInput`);
      linhas.push(`      id: ${id}`);
      linhas.push(`      displayName: ${JSON.stringify(s.label)}`);
      linhas.push(`      prompt:`);
      linhas.push(`        text: ${literal(s.prompt, 8)}`);
      linhas.push(`      variable: Local.${normalizeId(s.variable)}`);
    } else if (s.kind === "question") {
      linhas.push(`    - kind: Question`);
      linhas.push(`      id: ${id}`);
      linhas.push(`      displayName: ${JSON.stringify(s.label)}`);
      linhas.push(`      question:`);
      linhas.push(`        text: ${literal(s.text, 8)}`);
      linhas.push(`      variable: Local.${normalizeId(s.variable)}`);
    }
  }

  linhas.push("");
  linhas.push("    - kind: EndWorkflow");
  linhas.push("      id: fim");
  linhas.push("");
  return linhas.join("\n");
}

/** O que impede a publicação, dito ANTES de tentar.
 *
 * O backend valida pelo `WorkflowFactory` — que é o validador de verdade. Isto aqui não o
 * substitui: pega o que dá para pegar sem rede, para o erro comum não custar uma viagem.
 */
export function validate(flow: Flow): string[] {
  const problemas: string[] = [];
  const vistos = new Set<string>();

  if (flow.steps.length === 0) problemas.push("empty");

  for (const s of flow.steps) {
    const id = normalizeId(s.id);
    // `id` duplicado quebra `GotoAction`, que endereça por id — e o erro do runtime não diria
    // qual dos dois passos é o problema.
    if (vistos.has(id)) problemas.push(`dup:${id}`);
    vistos.add(id);
    if (s.kind === "agent" && !s.agent) problemas.push(`agent:${id}`);
    if (s.kind === "message" && !s.text.trim()) problemas.push(`text:${id}`);
    if (s.kind === "approval" && !s.prompt.trim()) problemas.push(`prompt:${id}`);
    if (s.kind === "question" && (!s.text.trim() || !s.variable.trim()))
      problemas.push(`question:${id}`);
  }

  // Um fluxo que só pergunta e nunca responde é sintaticamente válido e inútil.
  if (flow.steps.length > 0 && !flow.steps.some((s) => s.kind === "agent" || s.kind === "message"))
    problemas.push("noOutput");

  return problemas;
}

/** O YAML vira canvas — para EDITAR um fluxo que já existe.
 *
 * Parser deliberadamente raso: lê a sequência de ações de topo e ignora o que não sabe
 * representar (condições aninhadas, loops). Um fluxo com essas construções abre em modo leitura,
 * porque abri-lo no canvas e salvar por cima APAGARIA o que o canvas não entende — perder o
 * trabalho de alguém em silêncio é pior que recusar a edição.
 */
export function fromYaml(yaml: string): { flow: Flow; editable: boolean } {
  const steps: FlowStep[] = [];
  let editable = true;

  const blocos = yaml.split(/\n(?=\s*- kind:)/);
  for (const b of blocos) {
    const kind = /- kind:\s*(\w+)/.exec(b)?.[1];
    const id = /\n\s*id:\s*(\S+)/.exec(b)?.[1] ?? "";
    const label = /displayName:\s*"?([^"\n]+)"?/.exec(b)?.[1] ?? id;
    if (!kind) continue;
    if (kind === "InvokeAzureAgent") {
      const agent = /name:\s*(\S+)/.exec(b)?.[1] ?? "";
      const output = /responseObject:\s*Local\.(\S+)/.exec(b)?.[1];
      steps.push({ kind: "agent", id, label, agent, output });
    } else if (kind === "SendActivity") {
      steps.push({ kind: "message", id, label, text: "" });
    } else if (kind === "RequestExternalInput") {
      steps.push({ kind: "approval", id, label, prompt: "", variable: "aprovacao" });
    } else if (kind === "Question") {
      steps.push({ kind: "question", id, label, text: "", variable: "resposta" });
    } else if (kind === "EndWorkflow" || kind === "Workflow") {
      // esperado, não é passo
    } else {
      // ConditionGroup, Foreach, GotoAction, InvokeFunctionTool… O canvas não os representa
      // ainda, e salvar por cima os perderia.
      editable = false;
    }
  }

  return { flow: { steps }, editable };
}
