#!/usr/bin/env node
// Prova `lib/formflow/plan.ts` — o executor do plano de publicação declarado no manifesto.
//
// A FALHA PARCIAL É O QUE ELE EXISTE PARA ACERTAR. Publicar uma skill são duas chamadas; quando a
// segunda falha, a skill EXISTE. Uma tela que diz só "erro" faz a pessoa tentar de novo, e a
// segunda tentativa falha na PRIMEIRA operação, agora por nome duplicado, com uma mensagem que
// não tem nada a ver com o problema. Cada verificação abaixo é um pedaço desse caso.
//
//   npm run verify:plan

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "..", "lib", "formflow", "plan.ts"), "utf8");
const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "plan.ts",
});
const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => {});
const { executarPlano, resolverPath, pendentes } = mod.exports;

let falhas = 0;
const check = (nome, ok, detalhe = "") => {
  console.log(`${ok ? "OK  " : "FALHA"} · ${nome}${detalhe ? ` — ${detalhe}` : ""}`);
  if (!ok) falhas++;
};

// O plano do manifesto da skill, tal como ele é.
const PLANO = [
  { id: "create_skill", method: "POST", path: "/api/foundry/skills/{name}" },
  { id: "upload_bundle", method: "POST", path: "/api/foundry/skills/{name}", requires: ["create_skill"] },
];
const V = { name: "rollback-de-deploy" };

const st = (r, id) => r.operacoes.find((o) => o.id === id)?.status;

// ── tudo dá certo ──────────────────────────────────────────────────────────────────────────
{
  const chamadas = [];
  const r = await executarPlano(PLANO, V, async (op) => (chamadas.push(op.id), null));
  check("as duas operações rodam, na ordem", chamadas.join(",") === "create_skill,upload_bundle");
  check("as duas ficam feitas", r.feitas.length === 2);
  check("sucesso total NÃO é parcial", r.parcial === false);
}

// ── A SEGUNDA FALHA: o caso que motiva o arquivo ───────────────────────────────────────────
{
  const r = await executarPlano(PLANO, V, async (op) =>
    op.id === "upload_bundle" ? "413 payload too large" : null,
  );
  check("a primeira ficou de pé", st(r, "create_skill") === "feita");
  check("a segunda falhou", st(r, "upload_bundle") === "falhou");
  check("…com a mensagem do serviço", r.operacoes[1].erro === "413 payload too large");
  check("isto É parcial — a skill existe", r.parcial === true);
  check("`feitas` carrega o que sobreviveu", r.feitas.join() === "create_skill");
}

// ── A PRIMEIRA FALHA: a segunda é PULADA, não falhada ───────────────────────────────────────
{
  const chamadas = [];
  const r = await executarPlano(PLANO, V, async (op) => {
    chamadas.push(op.id);
    return op.id === "create_skill" ? "409 já existe" : null;
  });
  check("a segunda nem é chamada", chamadas.join() === "create_skill");
  // A distinção que importa: "não rodou porque a anterior não rodou" ≠ "rodou e deu erro".
  // Achatar as duas em `falhou` faria a pessoa procurar um problema onde não houve nenhum.
  check("a segunda fica PULADA, não falhada", st(r, "upload_bundle") === "pulada");
  check("nada ficou feito", r.feitas.length === 0);
  check("só falhas NÃO é parcial", r.parcial === false);
}

// ── RETENTATIVA: o que já rodou não roda de novo ───────────────────────────────────────────
{
  const chamadas = [];
  const r = await executarPlano(PLANO, V, async (op) => (chamadas.push(op.id), null), {
    feitas: ["create_skill"],
  });
  // Sem isto, a retentativa chamaria `create_skill` de novo e receberia "nome duplicado" — um
  // erro sobre o passo errado, que é como uma falha parcial vira um beco.
  check("não repete o que já deu certo", chamadas.join() === "upload_bundle");
  check("a anterior continua contando como feita", st(r, "create_skill") === "feita");
  check("agora sim, tudo feito", r.feitas.length === 2);
}

// ── SELEÇÃO: declarar não é executar ───────────────────────────────────────────────────────
{
  // O manifesto do `knowledge` declara `upload_files` E `import_repo` — a pessoa escolhe um dos
  // dois caminhos.
  const plano = [
    { id: "create_base" },
    { id: "upload_files", requires: ["create_base"] },
    { id: "import_repo", requires: ["create_base"] },
  ];
  const chamadas = [];
  await executarPlano(plano, {}, async (op) => (chamadas.push(op.id), null), {
    selecionadas: ["create_base", "import_repo"],
  });
  check("só as selecionadas rodam", chamadas.join() === "create_base,import_repo");
}

// ── o que a seção travada consulta ─────────────────────────────────────────────────────────
check("pendentes reflete o que falta", pendentes(PLANO, ["create_skill"]).join() === "upload_bundle");
check("pendentes vazio quando tudo rodou", pendentes(PLANO, ["create_skill", "upload_bundle"]).length === 0);

// ── o caminho é resolvido com os valores ───────────────────────────────────────────────────
check("interpola o caminho", resolverPath(PLANO[0], V) === "/api/foundry/skills/rollback-de-deploy");
// Um nome com barra viraria dois segmentos de rota e alcançaria outro recurso.
check("escapa o valor", resolverPath(PLANO[0], { name: "a/b" }) === "/api/foundry/skills/a%2Fb");

console.log(falhas ? `\n${falhas} verificação(ões) falharam.` : "\nTodas as verificações passaram.");
process.exit(falhas ? 1 : 0);
