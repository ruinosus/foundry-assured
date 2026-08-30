#!/usr/bin/env node
// Prova `lib/okf.ts` — o bloco de procedência que viaja no `metadata` da versão publicada, no
// vocabulário do OKF v0.2. Importa as funções DE VERDADE (transpiladas na hora), nunca uma cópia.
// Mesmo padrão de verify-highlight.mjs e verify-text-diff.mjs. Roda com:
//
//   npm run verify:okf
//
// O que ele guarda, e por que cada um está aqui:
//
//   1. o campo escrito SEM fonte continua aparecendo — é a razão de trocar o formato antigo, que
//      omitia esse campo e o tornava indistinguível de um campo digitado à mão;
//   2. `sources` é AUSENTE quando vazio, nunca `[]` — a spec trata ausente como "não declarado",
//      e uma lista vazia diz "derivei de nada", que é outra afirmação;
//   3. nenhuma origem ⇒ `null`, não um bloco vazio — um `{}` no metadata declararia procedência
//      sobre um documento inteiramente escrito à mão;
//   4. o `id` da fonte é estável e seguro para footnote (`[^id]`, SPEC §5.1);
//   5. o instante é ISO 8601 com offset — exigência da spec para todo campo de data;
//   6. a serialização é a string que o Foundry aceita (ele recusa objeto em `metadata`).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "..", "lib", "okf.ts"), "utf8");
const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "okf.ts",
});
const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => {});
const { buildProvenance, serializeProvenance } = mod.exports;

let falhas = 0;
const check = (nome, ok, detalhe = "") => {
  console.log(`${ok ? "OK  " : "FALHA"} · ${nome}${detalhe ? ` — ${detalhe}` : ""}`);
  if (!ok) falhas++;
};

const AT = "2026-08-30T12:00:00.000Z";

// 1 e 2 · com fonte e sem fonte
{
  const p = buildProvenance({
    instructions: { by: "builder", at: AT, sources: ["rh-politicas", "rh-politicas/ferias.md"] },
    description: { by: "builder", at: AT, sources: [] },
  });
  check("declara okf_version 0.2", p.okf_version === "0.2");
  check("o campo SEM fonte continua presente", "description" in p.fields);
  check("…e não ganha uma lista vazia", !("sources" in p.fields.description));
  check("o campo COM fonte lista as duas", p.fields.instructions.sources.length === 2);
  check("generated carrega quem e quando", p.fields.instructions.generated.by === "builder");

  // 4 · o id é derivado e seguro para footnote
  const ids = p.fields.instructions.sources.map((s) => s.id);
  check("id de fonte é slug", ids[0] === "rh-politicas" && ids[1] === "rh-politicas-ferias-md", ids.join(" · "));
  check("o resource preserva o original", p.fields.instructions.sources[1].resource === "rh-politicas/ferias.md");
  check("nenhum id vazio", ids.every((i) => i.length > 0));
}

// 3 · nada declarado ⇒ null
check("sem origem nenhuma devolve null", buildProvenance({}) === null);
check("…e a serialização também", serializeProvenance({}) === null);

// 5 · o instante atravessa como a spec pede
{
  const p = buildProvenance({ x: { by: "builder", at: AT, sources: [] } });
  check("instante ISO 8601 com zona", /Z$|[+-]\d{2}:\d{2}$/.test(p.fields.x.generated.at));
}

// 6 · a serialização é string e volta igual
{
  const s = serializeProvenance({ name: { by: "builder", at: AT, sources: ["kb"] } });
  check("serializa para string", typeof s === "string");
  const volta = JSON.parse(s);
  check("…e o round-trip preserva tudo", volta.fields.name.sources[0].resource === "kb");
}

// borda · fonte com caracteres que não formam slug
{
  const p = buildProvenance({ x: { by: "builder", at: AT, sources: ["///"] } });
  check("fonte impronunciável ainda recebe um id", p.fields.x.sources[0].id === "source");
}

console.log(falhas ? `\n${falhas} verificação(ões) falharam.` : "\nTodas as verificações passaram.");
process.exit(falhas ? 1 : 0);
