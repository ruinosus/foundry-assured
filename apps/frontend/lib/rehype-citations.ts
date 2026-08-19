// O `[n]` vira botão dentro da árvore hast, não no texto bruto.
//
// A versão anterior (MessageEvidence.tsx) fazia `content.split(/(\[\d{1,3}\])/g)` e renderizava
// CADA PEDAÇO num `MarkdownRenderer` independente — o que quebra qualquer markdown que atravesse
// uma fronteira de pedaço: tabela com `[n]` numa célula virava tabela de 1 linha + sintaxe crua,
// bloco cercado partido ao meio fechava a cerca cedo demais, lista com `[n]` virava N `<ol>`
// (numeração reiniciada), e o `[n]` de CÓDIGO (`argv[1]`, `A[1]` de Mermaid) virava botão porque
// o split não distinguia prosa de código.
//
// Este módulo troca a estratégia: UM único `MarkdownRenderer` para o conteúdo inteiro, e a
// substituição do marcador vira um rehype plugin — mexe na árvore JÁ PARSEADA (depois do
// Markdown virar hast), só em nós de TEXTO, pulando qualquer nó com ancestral `code`/`pre`. O
// resto do pipeline do Streamdown (tabela, lista, cerca de código, Mermaid) roda por cima sem
// saber que isso existe.
//
// Entra DEPOIS dos rehype plugins padrão do Streamdown (`defaultRehypePlugins`: raw → katex →
// sanitize → harden) porque o nó que injetamos é sintético, não veio de markdown do usuário — não
// há por que o sanitizer/harden da lib mexer nele, e rodar depois evita que um schema de
// sanitização futuro decida que `data-citation-*` é atributo desconhecido e o descarte.

import type { Citation } from "./citations";

const MARCADOR = /\[(\d{1,3})\]/g;

// `code`/`pre`: fronteira que o marcador nunca atravessa. `argv[1]` em bash e `A[1]` em Mermaid
// ficam texto de código, mesmo que o índice exista entre as citações da resposta.
const SEM_CITACAO = new Set(["code", "pre"]);

type NoTexto = { type: "text"; value: string };
type NoElemento = {
  type: "element";
  tagName: string;
  properties?: Record<string, unknown>;
  children?: NoFilho[];
};
type NoFilho = NoTexto | NoElemento | { type: string; [key: string]: unknown };
type ArvoreHast = { type: "root"; children: NoFilho[] };

function partirTexto(no: NoTexto, porIndice: Map<number, Citation>): NoFilho[] {
  MARCADOR.lastIndex = 0;
  if (!MARCADOR.test(no.value)) return [no];
  MARCADOR.lastIndex = 0;

  const partes: NoFilho[] = [];
  let ultimo = 0;
  let m: RegExpExecArray | null;
  while ((m = MARCADOR.exec(no.value))) {
    const indice = Number(m[1]);
    const citacao = porIndice.get(indice);
    if (m.index > ultimo) partes.push({ type: "text", value: no.value.slice(ultimo, m.index) });

    if (citacao) {
      // <data> — tag HTML real, mas que o Streamdown não usa para nada (sem componente padrão,
      // sem plugin remark que a produza), então hijack-á-la não colide com nenhum outro
      // markdown. O valor semântico ("dado de máquina associado a um texto legível") também cai
      // bem para "índice de citação".
      partes.push({
        type: "element",
        tagName: "data",
        properties: {
          "data-citation-index": citacao.index,
          "data-citation-title": citacao.title,
          "data-citation-snippet": citacao.snippet ?? "",
        },
        children: [{ type: "text", value: m[0] }],
      });
    } else {
      // Índice órfão (o modelo escreveu [13] com 12 documentos): fica TEXTO SIMPLES. Um botão
      // que não leva a lugar nenhum é pior do que nenhum botão.
      partes.push({ type: "text", value: m[0] });
    }
    ultimo = m.index + m[0].length;
  }
  if (ultimo < no.value.length) partes.push({ type: "text", value: no.value.slice(ultimo) });
  return partes;
}

function transformar(filhos: NoFilho[] | undefined, porIndice: Map<number, Citation>): NoFilho[] | undefined {
  if (!filhos) return filhos;
  const out: NoFilho[] = [];
  for (const filho of filhos) {
    if (filho.type === "text") {
      out.push(...partirTexto(filho as NoTexto, porIndice));
    } else if (filho.type === "element" && SEM_CITACAO.has((filho as NoElemento).tagName)) {
      // Conteúdo de código intocado — nem desce recursivamente.
      out.push(filho);
    } else if (filho.type === "element") {
      const el = filho as NoElemento;
      out.push({ ...el, children: transformar(el.children, porIndice) });
    } else {
      out.push(filho);
    }
  }
  return out;
}

// Attacher no formato padrão do unified: `(tree) => void`, aceito em `rehypePlugins` (tipo
// `PluggableList`, conferido em `node_modules/streamdown/dist/index.d.ts`).
export function rehypeCitations(citations: Citation[]) {
  const porIndice = new Map(citations.map((c) => [c.index, c]));
  return (tree: ArvoreHast) => {
    if (porIndice.size === 0) return; // sem citação: não percorre a árvore à toa
    tree.children = transformar(tree.children, porIndice) ?? tree.children;
  };
}
