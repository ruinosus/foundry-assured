#!/usr/bin/env node
// Prova `diffWords` (lib/text-diff.ts) — o diff que o card de proposta usa para mostrar o que
// muda no campo antes de a pessoa decidir. Importa a função DE VERDADE (transpilada na hora com
// o `typescript` já instalado), nunca uma cópia do algoritmo. Mesmo padrão de
// verify-highlight.mjs. Roda com:
//
//   npm run verify:text-diff
//
// O que ele guarda, e por que cada um está aqui:
//
//   1. juntar os pedaços reproduz o texto — se falhar, o diff MOSTRA um texto que não é o que
//      será gravado, que é a pior falha possível num card de decisão;
//   2. texto igual não produz mudança nenhuma — senão o card gritaria a cada proposta idêntica;
//   3. campo vazio vira tudo adição — é o caso mais comum (campo em branco recebendo a primeira
//      proposta) e não pode virar um diff de linha inteira;
//   4. a contagem ignora espaço — "+2 palavras" precisa contar palavras, não a quebra de linha
//      que se moveu junto;
//   5. o teto é DITO (`truncated`), nunca um diff silenciosamente errado.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "..", "lib", "text-diff.ts"), "utf8");
const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "text-diff.ts",
});
const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => {});
const { diffWords } = mod.exports;

let falhas = 0;
const check = (nome, ok, detalhe = "") => {
  console.log(`${ok ? "OK  " : "FALHA"} · ${nome}${detalhe ? ` — ${detalhe}` : ""}`);
  if (!ok) falhas++;
};

const junta = (r, ops) => r.parts.filter((p) => ops.includes(p.op)).map((p) => p.text).join("");

// 1 · reconstrução exata dos dois lados
{
  const antes = "Você responde dúvidas de RH citando a política de origem.";
  const depois =
    "Você atende dúvidas de RH consultando a base rh-politicas e cita sempre o documento de origem.";
  const r = diffWords(antes, depois);
  check("reconstrói o texto ANTES a partir de same+del", junta(r, ["same", "del"]) === antes);
  check("reconstrói o texto DEPOIS a partir de same+add", junta(r, ["same", "add"]) === depois);
  check("achou trecho em comum", r.parts.some((p) => p.op === "same" && p.text.includes("dúvidas")));
}

// 2 · igual não muda nada
{
  const t = "Texto idêntico dos dois lados, com  espaço  duplo e\nquebra de linha.";
  const r = diffWords(t, t);
  check("texto igual não gera adição nem remoção", r.added === 0 && r.removed === 0);
  check("texto igual é um único pedaço 'same'", r.parts.length === 1 && r.parts[0].op === "same");
}

// 3 · campo vazio
{
  const depois = "Primeira proposta para um campo em branco.";
  const r = diffWords("", depois);
  check("campo vazio: nenhum 'del'", !r.parts.some((p) => p.op === "del"));
  check("campo vazio: tudo é adição", junta(r, ["add"]) === depois);
  check("campo vazio: conta 7 palavras", r.added === 7, `contou ${r.added}`);
}

// 4 · contagem ignora espaço em branco
{
  const r = diffWords("uma duas", "uma duas tres quatro");
  check("acrescentar 2 palavras conta 2", r.added === 2, `contou ${r.added}`);
  check("nada foi removido", r.removed === 0, `contou ${r.removed}`);
}
{
  const r = diffWords("uma duas tres", "uma tres");
  check("remover 1 palavra conta 1", r.removed === 1, `contou ${r.removed}`);
}

// 5 · o teto é declarado, não silencioso
{
  const gigante = Array.from({ length: 4100 }, (_, i) => `p${i}`).join(" ");
  const r = diffWords(gigante, gigante + " fim");
  check("acima do teto devolve truncated", r.truncated === true);
  check("acima do teto não inventa pedaços", r.parts.length === 0);
  const ok = diffWords("curto", "curto e bom");
  check("abaixo do teto NÃO marca truncated", ok.truncated === false);
}

console.log(falhas ? `\n${falhas} verificação(ões) falharam.` : "\nTodas as verificações passaram.");
process.exit(falhas ? 1 : 0);
