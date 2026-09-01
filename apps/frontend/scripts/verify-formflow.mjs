#!/usr/bin/env node
// O GATE QUE DEFINE A CAMADA FORMFLOW: o motor não conhece campo nenhum.
//
//   uma linha `if (campo.id === "instructions")` em qualquer arquivo do motor significa que
//   estamos de volta a três wizards escritos à mão com um invólucro comum.
//
// Ele varre os arquivos do motor procurando os ids de campo REAIS — lidos dos manifestos em
// `apps/backend/agents/assured/flows/*.md`, nunca de uma lista escrita aqui. Um campo novo no
// documento passa a ser vigiado sem ninguém lembrar de acrescentá-lo.
//
// Três outras coisas que ele guarda, todas do tipo que falha em silêncio:
//
//   2. o vocabulário de REGRAS é o mesmo dos dois lados (frontend e o gate do backend). Uma regra
//      com nome errado carrega, não é aplicada, e o campo passa a aceitar qualquer coisa;
//   3. toda regra que os manifestos citam está implementada aqui;
//   4. toda chave de tradução que as regras emitem existe no dicionário — uma mensagem de erro
//      que renderiza a própria chave é pior que nenhuma.
//
//   npm run verify:formflow

import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONT = path.join(here, "..");
const FLOWS = path.join(FRONT, "..", "backend", "agents", "assured", "flows");

let falhas = 0;
const check = (nome, ok, detalhe = "") => {
  console.log(`${ok ? "OK  " : "FALHA"} · ${nome}${detalhe ? ` — ${detalhe}` : ""}`);
  if (!ok) falhas++;
};

// ── os ids e as regras, lidos dos manifestos de verdade ────────────────────────────────────
const manifestos = readdirSync(FLOWS).filter((f) => f.endsWith(".md"));
check("há manifestos para vigiar", manifestos.length > 0, `${FLOWS}`);

const ids = new Set();
const regrasCitadas = new Set();
for (const arq of manifestos) {
  const texto = readFileSync(path.join(FLOWS, arq), "utf8");
  for (const m of texto.matchAll(/^\s*- id:\s*(\w+)\s*$/gm)) ids.add(m[1]);
  for (const m of texto.matchAll(/rules:\s*\[([^\]]+)\]/g))
    for (const r of m[1].split(",")) regrasCitadas.add(r.trim());
}
// `parts:` e `plan:` também usam `- id:`; o que importa é que nenhum deles apareça no motor.
check("colheu ids de campo dos manifestos", ids.size > 5, `${ids.size} ids`);

// UM id pode COINCIDIR com o nome de um tipo de campo — `files` é as duas coisas: o tipo do
// controle e o id de um campo do fluxo `knowledge`. `campo.type === "files"` é legítimo (o motor
// PRECISA decidir por tipo), e textualmente indistinguível de `valores["files"]`, que não é.
// Esses ficam fora da varredura, e isso é uma limitação DECLARADA e não um silêncio: um campo
// chamado como um tipo é ambíguo por natureza, e a resposta certa é não nomeá-lo assim.
const TIPOS = ["text", "longtext", "choice", "multi", "pair", "files", "secret"];
const ambiguos = TIPOS.filter((t) => ids.has(t));
for (const t of ambiguos) ids.delete(t);
if (ambiguos.length) console.log(`      (fora da varredura, id = nome de tipo: ${ambiguos.join(", ")})`);

// ── 1 · o motor não menciona nenhum id ─────────────────────────────────────────────────────
const MOTOR = [
  "components/formflow/FormFlow.tsx",
  "lib/formflow/review.ts",
  "lib/formflow/rules.ts",
  "lib/formflow/types.ts",
];
// O que se procura é o ACOPLAMENTO, não a palavra. `manifest.name` e `file.name` são
// propriedades legítimas de outros objetos, e o tipo de campo `"files"` colide com o id de um
// campo chamado `files` — proibir a string crua reprovaria código correto e ensinaria a
// contornar o gate. O acoplamento real tem quatro formas, e são estas:
//
//     valores.<id>        valores["<id>"]        === "<id>"        case "<id>"
//
// Todas significam a mesma coisa: o motor decidiu alguma coisa por causa de QUAL campo é.
const ACOPLAMENTO = (id) => [
  new RegExp(`\\b(valores|values|origens|origins)\\.${id}\\b`),
  new RegExp(`\\b(valores|values|origens|origins)\\[\\s*["'\`]${id}["'\`]`),
  new RegExp(`[!=]==\\s*["'\`]${id}["'\`]`),
  new RegExp(`case\\s+["'\`]${id}["'\`]`),
];

for (const rel of MOTOR) {
  const texto = readFileSync(path.join(FRONT, rel), "utf8");
  // Comentários fora: eles EXPLICAM o acoplamento que não existe mais, e proibir a palavra num
  // comentário proibiria documentar a decisão.
  const codigo = texto.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  const achados = [...ids].filter((id) => ACOPLAMENTO(id).some((re) => re.test(codigo)));
  check(`${rel} não decide nada por qual campo é`, achados.length === 0, `acopla a: ${achados.join(", ")}`);
}

// E a prova de que o gate MORDE: o mesmo teste sobre um trecho que tem o acoplamento tem de
// reprovar. Um gate que só diz "ok" não distingue código limpo de regex quebrada.
{
  const sujo = 'if (campo.id === "instructions") { aplicar(valores.instructions); }';
  const pega = [...ids].some((id) => ACOPLAMENTO(id).some((re) => re.test(sujo)));
  check("o gate reprova um acoplamento de verdade", pega, "a regex não pegou o caso óbvio");
}

// ── 2/3 · o vocabulário de regras ──────────────────────────────────────────────────────────
const src = readFileSync(path.join(FRONT, "lib", "formflow", "rules.ts"), "utf8");
const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "rules.ts",
});
const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => {});
const { REGRAS, validarCampo } = mod.exports;

const implementadas = new Set(Object.keys(REGRAS));
const naoImplementadas = [...regrasCitadas].filter((r) => !implementadas.has(r));
check("toda regra citada nos manifestos existe", naoImplementadas.length === 0, `faltam: ${naoImplementadas}`);

// O espelho com o backend: a lista lá é `REGRAS` em tests/formflow/manifest_test.py.
const testePy = readFileSync(
  path.join(FRONT, "..", "backend", "tests", "formflow", "manifest_test.py"),
  "utf8",
);
const noBackend = new Set(
  [...(testePy.match(/^REGRAS = \{([^}]+)\}/m)?.[1] ?? "").matchAll(/"(\w+)"/g)].map((m) => m[1]),
);
const soFront = [...implementadas].filter((r) => !noBackend.has(r));
const soBack = [...noBackend].filter((r) => !implementadas.has(r));
check("o vocabulário de regras é o mesmo nos dois lados", soFront.length === 0 && soBack.length === 0,
      `só no front: ${soFront} · só no back: ${soBack}`);

// ── 4 · as mensagens existem no dicionário ─────────────────────────────────────────────────
const pt = JSON.parse(readFileSync(path.join(FRONT, "messages", "pt-BR.json"), "utf8")).formflow ?? {};
const chaves = new Set(["rule_required", "rule_unknown", ...[...implementadas].map((r) => `rule_${r}`)]);
const semTraducao = [...chaves].filter((k) => !(k in pt));
check("toda mensagem de regra está traduzida", semTraducao.length === 0, `sem tradução: ${semTraducao}`);

// ── as regras fazem o que dizem ────────────────────────────────────────────────────────────
const campo = (extra) => ({ required: true, rules: ["resourceName", "max63", "unique"], ...extra });
check("campo obrigatório vazio → required", validarCampo("", campo(), {})?.key === "rule_required");
check("campo opcional vazio → sem erro", validarCampo("", { rules: ["resourceName"] }, {}) === null);
check("maiúscula → resourceName", validarCampo("Suporte-RH", campo(), {})?.key === "rule_resourceName");
check("64 caracteres → max63", validarCampo("a".repeat(64), campo(), {})?.key === "rule_max63");
check("nome existente → unique",
      validarCampo("helpdesk", campo(), { taken: ["helpdesk"] })?.key === "rule_unique");
check("nome válido e livre → sem erro", validarCampo("suporte-rh", campo(), { taken: ["x"] }) === null);
// A ordem importa: `resourceName` antes de `unique` — dizer "já existe" sobre um nome que nem é
// válido manda a pessoa trocar de nome em vez de corrigir o formato.
check("a primeira regra da lista é a que fala",
      validarCampo("Suporte RH", campo(), { taken: ["Suporte RH"] })?.key === "rule_resourceName");
check("travessia de diretório → safeFilename",
      validarCampo("../etc/passwd", { rules: ["safeFilename"] }, {})?.key === "rule_safeFilename");
check("arquivo comum passa", validarCampo("rollback.sh", { rules: ["safeFilename"] }, {}) === null);
check("AgentSchema exige documento YAML seguro",
  validarCampo("../agent.yaml", { rules: ["agentSchemaReference"] }, {})?.key === "rule_agentSchemaReference");
check("workflow aceita documento YAML",
  validarCampo("workflows/review.yml", { rules: ["workflowReference"] }, {}) === null);
check("container exige digest SHA-256 completo",
  validarCampo("registry/app:latest", { rules: ["containerImageReference"] }, {})?.key === "rule_containerImageReference");
check("container aceita referência imutável",
  validarCampo(`registry/app@sha256:${"a".repeat(64)}`, { rules: ["containerImageReference"] }, {}) === null);
// Uma regra que o motor não conhece FALA, em vez de ser ignorada — é o modo de falha que o
// espelho acima existe para impedir, e este é o comportamento quando ele falhar mesmo assim.
check("regra desconhecida não passa calada",
      validarCampo("x", { rules: ["naoExiste"] }, {})?.key === "rule_unknown");

console.log(falhas ? `\n${falhas} verificação(ões) falharam.` : "\nTodas as verificações passaram.");
process.exit(falhas ? 1 : 0);
