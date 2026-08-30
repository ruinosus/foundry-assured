#!/usr/bin/env node
// A matriz de recursos do motor não pode mentir — nem inventar, nem esconder.
//
// A REGRA DE DESIGN QUE ELA CARREGA, e que este gate protege:
//
//     "não precisa" NÃO é "não cumpre".
//
// Um copiloto de RH não fica pior por não ter trilha encadeada — ele não tem peça probatória a
// sustentar. Por isso a matriz separa dois LADOS e não dá nota. Se alguém acrescentar uma
// pontuação ou uma fração, ausência legítima vira dívida, e a primeira reação de quem lê é
// declarar recursos que o domínio não pede — o oposto de um manifesto honesto.
//
// O que o gate guarda:
//
//   1. TODO recurso cai num dos dois lados. Um recurso sem lado some da tela, e o que some não é
//      questionado;
//   2. TODO recurso tem detalhe, nos dois lados. "Não precisa" sem motivo é indistinguível de
//      "esqueceram" — e é exatamente a informação que faz a ausência ser lida como decisão;
//   3. o lado é DERIVADO do documento, não de um default. Um copiloto vazio não pode aparecer
//      usando nada, e um copiloto completo não pode aparecer precisando de tudo;
//   4. toda chave de tradução que a matriz emite existe no dicionário.
//
//   npm run verify:copilot-matrix

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONT = path.join(here, "..");
const src = readFileSync(path.join(FRONT, "lib", "copilot.ts"), "utf8");
const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "copilot.ts",
});
const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => {});
const { recursosDoMotor } = mod.exports;

let falhas = 0;
const check = (nome, ok, detalhe = "") => {
  console.log(`${ok ? "OK  " : "FALHA"} · ${nome}${detalhe ? ` — ${detalhe}` : ""}`);
  if (!ok) falhas++;
};

// O tradutor de teste devolve a CHAVE, para que o gate veja qual foi pedida.
const chavesPedidas = new Set();
const t = (k, v) => {
  chavesPedidas.add(k);
  return v ? `${k}(${Object.values(v).join(",")})` : k;
};

// ── um copiloto VAZIO: nada declarado ──────────────────────────────────────────────────────
{
  const m = recursosDoMotor({ name: "vazio" }, t);
  check("todo recurso aparece mesmo num copiloto vazio", m.length >= 8, `${m.length}`);
  check("…e nenhum deles é marcado como usado", m.every((r) => !r.usa));
  check("…mas TODOS têm detalhe", m.every((r) => r.detalhe && r.detalhe.length > 0));
}

// ── o copiloto REAL do repositório ─────────────────────────────────────────────────────────
{
  const doc = readFileSync(
    path.join(FRONT, "..", "backend", "agents", "assured", "copilots", "builder.md"),
    "utf8",
  );
  // Reconstrói só o que a matriz consulta, do documento de verdade — assim o gate acompanha o
  // manifesto em vez de uma cópia que envelhece.
  const c = {
    name: "builder",
    targets: [...doc.matchAll(/writes: \[([^\]]+)\]/g)].map((mm) => ({
      writes: mm[1].split(",").map((s) => s.trim()),
    })),
    tools: { write: [] },
    grounding: { bases: [], refuseWithoutSource: false },
    surface: { screens: (doc.match(/screens: \[([^\]]+)\]/) ?? [, ""])[1].split(",").map((s) => s.trim()).filter(Boolean) },
    policy: (doc.match(/^policy: (\w+)/m) ?? [, ""])[1] || undefined,
    engine: { runtime: (doc.match(/runtime: (\w+)/) ?? [, ""])[1] || undefined },
    measurement: { record: /record: POST/.test(doc) ? "POST /builder-assist/proposals" : undefined },
  };
  const m = recursosDoMotor(c, t);
  const usa = m.filter((r) => r.usa).map((r) => r.id);
  const nao = m.filter((r) => !r.usa).map((r) => r.id);

  check("o builder USA a proposta de campo", usa.includes("proposta"), usa.join(","));
  check("…declara superfície", usa.includes("superficie_declarada"));
  check("…herda política", usa.includes("politica_herdada"));
  check("…declara runtime", usa.includes("runtime_declarado"));
  // As ausências do builder são REAIS e são o ponto: ele não escreve em sistema de fora e não
  // consulta base nenhuma. A matriz precisa mostrar isso como escolha, não como buraco.
  check("o builder NÃO precisa de tool de escrita", nao.includes("escrita_com_gate"), nao.join(","));
  check("…nem de base de conhecimento", nao.includes("fundamentacao"));
  check("os dois lados somam o total", usa.length + nao.length === m.length);
  check("nenhum lado está vazio (senão a matriz vira uma lista)", usa.length > 0 && nao.length > 0);
  check("todo recurso do lado 'não precisa' explica por quê",
        m.filter((r) => !r.usa).every((r) => r.detalhe.length > 0));
}

// ── 3 · o lado é derivado, não default ─────────────────────────────────────────────────────
{
  const cheio = recursosDoMotor(
    {
      name: "cheio",
      targets: [{ flow: "f", writes: ["a", "b"] }],
      tools: { write: [{ name: "criar", require_approval: "always", role: "Approver" }] },
      grounding: { bases: ["kb"], refuseWithoutSource: true },
      surface: { screens: ["/x"] },
      policy: "hitl",
      engine: { runtime: "foundry" },
      measurement: { record: "POST /x", outcomes: ["accepted"] },
    },
    t,
  );
  check("um copiloto completo usa TUDO", cheio.every((r) => r.usa), cheio.filter((r) => !r.usa).map((r) => r.id).join(","));
}

// ── 4 · as chaves existem no dicionário ────────────────────────────────────────────────────
{
  const pt = JSON.parse(readFileSync(path.join(FRONT, "messages", "pt-BR.json"), "utf8")).copilots ?? {};
  const faltando = [...chavesPedidas].map((k) => k.split("(")[0]).filter((k) => !(k in pt));
  check("toda chave da matriz está traduzida", faltando.length === 0, `sem tradução: ${faltando}`);
  // E o rótulo de cada recurso, que a tela pede por `recurso_<id>`.
  const ids = recursosDoMotor({ name: "x" }, t).map((r) => `recurso_${r.id}`);
  const semRotulo = ids.filter((k) => !(k in pt));
  check("todo recurso tem rótulo traduzido", semRotulo.length === 0, `${semRotulo}`);
}

// ── a regra de design, guardada literalmente ───────────────────────────────────────────────
{
  const tela = readFileSync(path.join(FRONT, "components", "copilots", "CopilotResource.tsx"), "utf8");
  const codigo = tela.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  // Uma fração ou porcentagem na matriz seria a pontuação que o desenho recusa.
  const pontua = /(usa|recursos)\.length\s*\+\s*['"`]\s*\/|toFixed|%\s*<\/|Math\.round\([^)]*length/.test(codigo);
  check("a matriz não pontua nem mostra fração", !pontua, "achei algo que parece uma nota");
}

console.log(falhas ? `\n${falhas} verificação(ões) falharam.` : "\nTodas as verificações passaram.");
process.exit(falhas ? 1 : 0);
