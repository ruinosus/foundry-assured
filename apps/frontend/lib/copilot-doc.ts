// @gera-formato-externo — este arquivo produz YAML de um documento OKF. As palavras aqui são
// CONTRATO daquele formato (`openByDefault`, `citation: optional`), não texto de tela; traduzi-las
// quebraria a saída.
//
// Monta o documento OKF de um copiloto a partir dos valores do formulário.
//
// A SAÍDA É O DOCUMENTO, NÃO UM PUSH — e isso não é uma etapa faltando, é o desenho.
//
// Um copiloto é um documento do BUNDLE, e o bundle vive no repositório. Gravá-lo do servidor
// esbarra em duas coisas que este produto já decidiu: em produção o disco do container é
// efêmero ou read-only (ADR-021 documenta um fluxo que sumia no restart exatamente assim), e
// documento publicado não é editado — revisão cria versão, e versão de arquivo é commit.
//
// É a mesma saída que o editor de bundle dos mocks descreve: *"o editor grava por okf-to-git: PR
// no repositório canônico. Não há push, nem gravação direta em runtime."* O PR automático é o
// passo seguinte; o documento correto é o que falta para ele existir.

import type { Valores } from "@/lib/formflow/types";

/** Aspas em valor de texto: sem elas, um título com `:` é YAML inválido — e o parser do backend
 *  levanta alto em vez de engolir, que é como esse erro aparece. */
function aspas(s: string): string {
  return '"' + s.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
}

/** Agrupa `formulario.campo` em um alvo por formulário. Espelha `alvos_de` no backend — e é a
 *  única duplicação aqui, porque a tela precisa PREVER o documento antes de existir servidor
 *  para montá-lo. O gate compara os dois. */
export function agruparAlvos(selecionados: string[]): { flow: string; writes: string[] }[] {
  const porFlow = new Map<string, string[]>();
  for (const item of selecionados) {
    const i = item.indexOf(".");
    if (i <= 0) continue;
    const flow = item.slice(0, i);
    const campo = item.slice(i + 1);
    if (!campo) continue;
    porFlow.set(flow, [...(porFlow.get(flow) ?? []), campo]);
  }
  return [...porFlow.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([flow, writes]) => ({ flow, writes: [...writes].sort() }));
}

/** O documento OKF, pronto para virar arquivo. */
export function montarDocumento(v: Valores): string {
  const txt = (id: string) => String(v[id] ?? "").trim();
  const lista = (id: string) => (v[id] as string[] | undefined) ?? [];
  const alvos = agruparAlvos(lista("writes"));

  const L: string[] = [
    "---",
    "type: copilot",
    `title: ${aspas(txt("title") || txt("name"))}`,
    `description: ${aspas(txt("description"))}`,
    `resource: ${txt("name")}`,
    "---",
    "",
    `# ${txt("title") || txt("name")}`,
    "",
    txt("description"),
    "",
    "## Spec",
    "",
    "```yaml",
    "surface:",
    `  mount: ${aspas(txt("mount"))}`,
    `  screens: [${lista("screens").join(", ")}]`,
    "  openByDefault: false",
    "",
    "engine:",
    `  agent: ${txt("agent")}`,
    "  protocol: AG-UI",
    `  runtime: ${txt("runtime")}`,
    "",
    "grounding:",
    "  bases: []",
    "  citation: optional",
    "  refuseWithoutSource: false",
    "",
    "targets:",
  ];

  if (!alvos.length) {
    // Lista vazia EXPLÍCITA, e o comentário diz o que ela significa. Um `targets:` sem nada
    // embaixo é YAML nulo, e nulo aqui seria lido como "não declarei" em vez de "não escreve".
    L.push("  []                    # sem alvo: ele conversa e não escreve nada");
  } else {
    for (const a of alvos) {
      L.push(`  - flow: ${a.flow}`);
      L.push(`    writes: [${a.writes.join(", ")}]`);
      L.push("    validateAgainst: field.rules");
    }
  }

  L.push(
    "",
    "tools:",
    "  read: []",
    "  write: []",
    "",
    "voice:",
    "  language: pt-BR",
    "  declareBeforeActing: true",
    "",
    "measurement:",
    "  record: POST /builder-assist/proposals",
    "  outcomes: [accepted, edited, discarded]",
    "",
    "policy: hitl",
    "```",
    "",
  );
  return L.join("\n");
}

/** Onde o documento deve ir. A tela mostra isto junto do conteúdo — um markdown sem o caminho
 *  obriga quem for salvar a adivinhar, e adivinhar caminho é como um bundle ganha uma casa
 *  errada. */
export function caminhoDoDocumento(v: Valores): string {
  return `apps/backend/agents/assured/copilots/${String(v.name ?? "sem-nome").trim()}.md`;
}
