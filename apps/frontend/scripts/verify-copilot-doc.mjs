#!/usr/bin/env node
// O documento que a tela monta tem de VOLTAR — carregar no backend e passar na verificação.
//
// ESTE É O ÚNICO GATE QUE FECHA O CICLO. A tela monta o YAML no browser; o loader do backend o lê
// e `verificar_alvos` o julga. São dois lados, dois idiomas, e nada garante que produzam a mesma
// coisa — um `title` com dois-pontos sem aspas, um `targets:` vazio que vira nulo, um campo
// agrupado diferente, e o copiloto criado pela tela é um copiloto que o produto recusa.
//
// O gate escreve o documento num diretório temporário e roda o loader DE VERDADE por cima
// (`AGENTS_DIR` aponta o loader para lá), em vez de comparar strings. Comparar strings provaria
// que o gerador não mudou; isto prova que ele produz algo que o consumidor aceita.
//
//   npm run verify:copilot-doc

import { mkdtempSync, mkdirSync, writeFileSync, cpSync, rmSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONT = path.join(here, "..");
const BACK = path.join(FRONT, "..", "backend");

// O módulo importa só TIPOS do formflow; a linha some no transpile e não vira `require`.
const src = readFileSync(path.join(FRONT, "lib", "copilot-doc.ts"), "utf8").replace(/^import type .*$/gm, "");
const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "copilot-doc.ts",
});
const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => ({}));
const { montarDocumento, agruparAlvos, caminhoDoDocumento } = mod.exports;

let falhas = 0;
const check = (nome, ok, detalhe = "") => {
  console.log(`${ok ? "OK  " : "FALHA"} · ${nome}${detalhe ? ` — ${detalhe}` : ""}`);
  if (!ok) falhas++;
};

// ── o agrupamento bate com o do backend ────────────────────────────────────────────────────
{
  const meu = agruparAlvos(["agent.name", "skill.description", "agent.instructions"]);
  const py = JSON.parse(
    execFileSync("uv", ["run", "--no-sync", "python", "-c",
      "import json;from app.modules.formflow.public import alvos_de;" +
      "print(json.dumps(alvos_de(['agent.name','skill.description','agent.instructions'])))"],
      { cwd: BACK, encoding: "utf8" }).trim().split("\n").pop());
  const meuNorm = JSON.stringify(meu.map((a) => ({ flow: a.flow, writes: a.writes })));
  const pyNorm = JSON.stringify(py.map((a) => ({ flow: a.flow, writes: a.writes })));
  check("o agrupamento da tela bate com o do backend", meuNorm === pyNorm, `${meuNorm} vs ${pyNorm}`);
}

// ── o documento carrega de volta, e passa na verificação ───────────────────────────────────
const casos = [
  {
    nome: "completo",
    v: {
      name: "atendimento-rh", title: "Copiloto de RH", description: "Ajuda o time de RH.",
      mount: "dock lateral", screens: ["/agents", "/knowledge"], agent: "builder", runtime: "backend",
      writes: ["agent.name", "agent.instructions", "knowledge.description"],
    },
    esperaProblemas: 0,
  },
  {
    // Um copiloto sem alvo é LEGÍTIMO: conversa e não escreve. O `targets: []` explícito é o que
    // impede o YAML de virar nulo — nulo seria lido como "não declarei" em vez de "não escreve".
    nome: "sem alvo",
    v: { name: "so-conversa", title: "Só conversa", description: "", mount: "console", screens: [], agent: "builder", runtime: "backend", writes: [] },
    esperaProblemas: 0,
  },
  {
    // O caso que quebra YAML se o gerador esquecer as aspas.
    nome: "título com dois-pontos",
    v: { name: "com-dois-pontos", title: "Runbook: recuperação de acesso", description: 'aspas "dentro" também', mount: "console", screens: [], agent: "builder", runtime: "backend", writes: ["agent.name"] },
    esperaProblemas: 0,
  },
];

const tmp = mkdtempSync(path.join(tmpdir(), "copilot-doc-"));
try {
  // O loader precisa dos FORMULÁRIOS reais ao lado, porque `verificar_alvos` os consulta.
  cpSync(path.join(BACK, "agents", "assured", "flows"), path.join(tmp, "flows"), { recursive: true });
  mkdirSync(path.join(tmp, "copilots"), { recursive: true });

  for (const caso of casos) {
    const doc = montarDocumento(caso.v);
    writeFileSync(path.join(tmp, "copilots", `${caso.v.name}.md`), doc, "utf8");
    check(`[${caso.nome}] o caminho aponta para copilots/`,
          caminhoDoDocumento(caso.v).endsWith(`copilots/${caso.v.name}.md`));

    const out = execFileSync("uv", ["run", "--no-sync", "python", "-c",
      "import json;from app.modules.formflow.public import load_copilot, verificar_alvos;" +
      `c=load_copilot('${caso.v.name}');print(json.dumps({'alvos':len(c.get('targets') or []),'problemas':verificar_alvos(c),'runtime':(c.get('engine') or {}).get('runtime'),'policy':c.get('policy'),'title_ok':True}))`],
      { cwd: BACK, encoding: "utf8", env: { ...process.env, AGENTS_DIR: tmp } });
    const r = JSON.parse(out.trim().split("\n").pop());

    check(`[${caso.nome}] o backend CARREGA o documento`, true);
    check(`[${caso.nome}] sem problema de alvo`, r.problemas.length === caso.esperaProblemas, JSON.stringify(r.problemas));
    check(`[${caso.nome}] declara runtime`, r.runtime === caso.v.runtime, String(r.runtime));
    check(`[${caso.nome}] herda a política`, r.policy === "hitl", String(r.policy));
  }

  // ── e o gate MORDE: um alvo inválido tem de ser reprovado ────────────────────────────────
  // A tela não deixa escolher isto (a lista vem do serviço), mas o documento pode ser editado à
  // mão — e é aí que a verificação precisa continuar valendo.
  const torto = montarDocumento({
    name: "torto", title: "Torto", description: "", mount: "console", screens: [],
    agent: "builder", runtime: "backend", writes: ["agent.model", "agent.nao-existe"],
  });
  writeFileSync(path.join(tmp, "copilots", "torto.md"), torto, "utf8");
  const out = execFileSync("uv", ["run", "--no-sync", "python", "-c",
    "import json;from app.modules.formflow.public import load_copilot, verificar_alvos;" +
    "print(json.dumps(verificar_alvos(load_copilot('torto'))))"],
    { cwd: BACK, encoding: "utf8", env: { ...process.env, AGENTS_DIR: tmp } });
  const ps = JSON.parse(out.trim().split("\n").pop());
  check("documento com dois alvos inválidos → dois problemas", ps.length === 2, JSON.stringify(ps));
  check("…reclama do campo que não aceita proposta", ps.some((p) => p.includes("ai: true")));
  check("…e do campo que não existe", ps.some((p) => p.includes("nao-existe")));
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

console.log(falhas ? `\n${falhas} verificação(ões) falharam.` : "\nTodas as verificações passaram.");
process.exit(falhas ? 1 : 0);
