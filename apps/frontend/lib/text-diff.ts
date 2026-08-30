// Diff palavra a palavra entre o texto que está no campo e o que o agente propôs.
//
// POR QUE ELE EXISTE. O card de proposta mostrava só o texto novo. Quem decide precisava manter
// na cabeça o que já estava escrito para saber o que ia mudar — e, num campo de instruções com
// nove linhas, ninguém mantém. Aceitar sem enxergar a diferença não é revisão; é confiança.
//
// POR QUE PALAVRA, E NÃO LINHA NEM CARACTERE. Os campos que o agente escreve são prosa
// (`instructions`, `description`), não código. Diff por LINHA marca o parágrafo inteiro como
// trocado quando uma palavra mudou; diff por CARACTERE quebra palavras no meio e produz um
// mosaico ilegível. Palavra é a unidade em que a pessoa lê e em que a mudança faz sentido.
//
// POR QUE NÃO UMA BIBLIOTECA. O algoritmo é uma LCS de vinte linhas sobre entradas que o
// formulário limita (um campo de texto, não um arquivo). Trazer uma dependência para isso pagaria
// auditoria de supply chain por código que cabe aqui — e a MÁXIMA MAIOR vale para plataforma, não
// obriga a importar um pacote de npm para cada função.
//
// O separador preserva o espaço em branco (`\s+` capturado) para que juntar os pedaços de volta
// reproduza o texto original byte a byte — sem isso, "igual" apareceria como mudança de espaço.

export type DiffOp = "same" | "add" | "del";

export interface DiffPart {
  op: DiffOp;
  text: string;
}

/** Quebra em palavras MANTENDO os espaços como itens próprios, para que a junção seja exata. */
function tokenize(s: string): string[] {
  return s.length ? s.split(/(\s+)/).filter((t) => t.length > 0) : [];
}

/** Teto de tokens por lado. Acima disso a LCS quadrática deixa de ser instantânea, e um campo de
 *  formulário que trava a aba é pior que um campo sem diff. Passando do teto, o chamador recebe
 *  `truncated` e mostra os textos lado a lado em vez do diff. */
const MAX_TOKENS = 4000;

export interface DiffResult {
  parts: DiffPart[];
  /** Quantas palavras (não espaços) entraram e saíram — é o que o resumo mostra. */
  added: number;
  removed: number;
  /** true quando o texto passou do teto e o diff NÃO foi calculado. Dito, nunca silencioso. */
  truncated: boolean;
}

/** Diff palavra a palavra de `antes` para `depois`. */
export function diffWords(antes: string, depois: string): DiffResult {
  const a = tokenize(antes);
  const b = tokenize(depois);

  if (a.length > MAX_TOKENS || b.length > MAX_TOKENS) {
    return { parts: [], added: 0, removed: 0, truncated: true };
  }

  // LCS clássica. `m[i][j]` = tamanho da maior subsequência comum entre a[i..] e b[j..].
  const m: number[][] = Array.from({ length: a.length + 1 }, () =>
    Array.from({ length: b.length + 1 }, () => 0),
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      m[i][j] = a[i] === b[j] ? m[i + 1][j + 1] + 1 : Math.max(m[i + 1][j], m[i][j + 1]);
    }
  }

  const parts: DiffParts = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push(parts, "same", a[i]);
      i++;
      j++;
    } else if (m[i + 1][j] >= m[i][j + 1]) {
      push(parts, "del", a[i]);
      i++;
    } else {
      push(parts, "add", b[j]);
      j++;
    }
  }
  while (i < a.length) push(parts, "del", a[i++]);
  while (j < b.length) push(parts, "add", b[j++]);

  // Conta só palavras: espaço que mudou de lugar não é informação para quem revisa.
  const conta = (op: DiffOp) =>
    parts.filter((p) => p.op === op).reduce((n, p) => n + p.text.split(/\s+/).filter(Boolean).length, 0);

  return { parts, added: conta("add"), removed: conta("del"), truncated: false };
}

type DiffParts = DiffPart[];

/** Acumula no último pedaço quando a operação é a mesma — senão o resultado sairia com um item
 *  por palavra e a renderização criaria centenas de spans para um parágrafo. */
function push(parts: DiffParts, op: DiffOp, text: string): void {
  const ultimo = parts[parts.length - 1];
  if (ultimo && ultimo.op === op) ultimo.text += text;
  else parts.push({ op, text });
}
