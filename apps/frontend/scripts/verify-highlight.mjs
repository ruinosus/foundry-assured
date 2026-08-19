#!/usr/bin/env node
// Prova, contra jsdom real, que `realcar` (lib/source-highlight.ts) atravessa fronteira de
// bloco corretamente. Não é parte dos gates de CI (não há test runner neste projeto) — é o
// script que produziu a tabela colada no relatório da revisão. Roda com:
//
//   node scripts/verify-highlight.mjs
//
// Importa a função de verdade (transpilada na hora com o `typescript` já instalado — sem
// bundler, sem recopiar o algoritmo para dentro do script) e afirma sobre o DOM resultante,
// não sobre uma cópia do algoritmo.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";
import { JSDOM } from "jsdom";

const here = path.dirname(fileURLToPath(import.meta.url));
const srcPath = path.join(here, "..", "lib", "source-highlight.ts");
const src = readFileSync(srcPath, "utf8");

const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "source-highlight.ts",
});

// Instancia um DOM real e expõe os globais que `realcar` usa (document, Text, NodeFilter,
// window) antes de executar o módulo transpilado — mesma técnica de qualquer setup jsdom de
// test runner, só que sem o test runner.
const dom = new JSDOM("<!doctype html><html><body></body></html>", { pretendToBeVisual: true });
const { window } = dom;
window.matchMedia = () => ({ matches: false });
// jsdom não implementa scrollIntoView — não é o que este script prova, então vira no-op.
window.Element.prototype.scrollIntoView = () => {};
global.window = window;
global.document = window.document;
global.Text = window.Text;
global.Node = window.Node;
global.NodeFilter = window.NodeFilter;
global.Element = window.Element;
global.HTMLElement = window.HTMLElement;

const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => {});
const { realcar } = mod.exports;

// ASSERÇÃO EXATA, não percentual (item 8 da faxina). A métrica antiga (`marcadoLen / alvoLen`,
// piso `< 0.9`) misturava DUAS coisas que não têm nada a ver uma com a outra:
//
//   1. ESPAÇO ENTRE NÓS: quando o realce atravessa fronteira de elemento (ex.: "<p>...tecnico
//      de plantao</p>" com `<strong>` no meio), cada `<mark>` marca só o texto DENTRO do seu
//      próprio nó — o espaço/quebra ENTRE os nós nunca pertence a nenhum `textContent`, então
//      somar os comprimentos dos `<mark>`s fica sistematicamente um pouco ABAIXO do trecho
//      normalizado, mesmo com realce PERFEITO e zero truncagem.
//   2. TRUNCAGEM DE VERDADE: o realce parou no meio do trecho e um pedaço real ficou de fora.
//
// Como (1) sempre desconta alguns pontos por caso mesmo sem bug, o piso tinha que ser frouxo
// (90%) só para não acusar (1) como falha — e essa mesma folga escondia (2): uma truncagem real
// de até 10% passava batido (foi como o achado descreveu "corta no meio da palavra, cobre 43%"
// SEM o gate acusar, porque não havia gate automático — só a tabela de revisão manual). E no
// sentido contrário, um caso a 1,2pp do piso quebra o gate por acrescentar duas palavras à
// fixture, sem regressão nenhuma no código.
//
// A troca: juntar o texto de TODOS os `<mark>`s (sem separador — cada um já carrega seu próprio
// texto) e comparar com o trecho, os DOIS COM ESPAÇO COLAPSADO (`replace(/\s+/g, "")`). Colapsar
// espaço dos dois lados elimina o problema (1) por construção — não há mais "espaço entre nós"
// para contar contra nada — enquanto qualquer palavra de verdade faltando (2) ainda quebra a
// igualdade, porque aquele texto literalmente não está em nenhum `<mark>`.
function marcado(container, trecho) {
  const marks = [...container.querySelectorAll("mark.source-hit")];
  const texto = marks.map((m) => m.textContent).join("").replace(/\s+/g, "");
  const esperado = trecho.replace(/\s+/g, "");
  return { count: marks.length, texts: marks.map((m) => m.textContent), bateExato: texto === esperado };
}

const casos = [
  {
    nome: "<p> com <strong> no meio",
    html: `<p>O runbook de rede exige que o time <strong>tecnico de plantao</strong> valide o roteador antes de qualquer reinicio programado.</p>`,
    trecho: "que o time tecnico de plantao valide o roteador antes de qualquer reinicio",
  },
  {
    nome: "<pre><code> tokenizado (Shiki)",
    html: `<pre><code><span class="line"><span>function</span> <span>reinicia</span><span>(</span><span>servico</span><span>)</span> <span>{</span></span>
<span class="line">  <span>return</span> <span>chamarApi</span><span>(</span><span>servico</span><span>)</span><span>;</span></span>
<span class="line"><span>}</span></span></code></pre>`,
    trecho: "function reinicia(servico) { return chamarApi(servico); }",
  },
  {
    nome: "dois <p>, trecho atravessando",
    html: `<p>O procedimento de rollback comeca pela validacao do ambiente tecnico.</p><p>Segunda etapa e notificar o time de plantao antes de aplicar a reversao.</p>`,
    trecho: "validacao do ambiente tecnico. Segunda etapa e notificar o time de plantao",
  },
  {
    nome: "<ul> com dois <li>",
    html: `<ul><li>Primeiro passo: isolar o servico com problema antes de qualquer alteracao.</li><li>Segundo passo: aplicar o patch validado em ambiente de homologacao.</li></ul>`,
    trecho: "isolar o servico com problema antes de qualquer alteracao. Segundo passo: aplicar o patch validado",
  },
  {
    nome: "<table> com duas <td>",
    html: `<table><tbody><tr><td>Codigo do incidente critico registrado pelo time</td><td>Responsavel designado para a correcao imediata</td></tr></tbody></table>`,
    trecho: "Codigo do incidente critico registrado pelo time Responsavel designado para a correcao",
  },
  {
    // Item 9 da faxina: <br> não é elemento de bloco (não entra em ELEMENTOS_BLOCO), mas produz
    // quebra visual dentro do MESMO <p> — sem tratamento, "plantao<br>Encerrar" colava sem
    // espaço e o realce truncava no meio. Não alcançável hoje (nenhum documento do corpus usa
    // <br>, Streamdown não liga remark-breaks), mas prova que o tratamento existe e não
    // regride em silêncio no dia em que alguém escrever um hard break.
    nome: "<p> com <br> no meio (hard break)",
    html: `<p>Primeiro passo: acionar o time de plantao.<br>Segundo passo: encerrar o incidente no painel.</p>`,
    trecho: "acionar o time de plantao. Segundo passo: encerrar o incidente",
  },
];

console.log("caso | encontrou | nós marcados | trecho intacto | texto marcado");
console.log("-----|-----------|--------------|-----------------|---------------");
let algumaFalha = false;
for (const c of casos) {
  const container = document.createElement("div");
  container.innerHTML = c.html;
  document.body.appendChild(container);
  const achou = realcar(container, c.trecho);
  const { count, texts, bateExato } = marcado(container, c.trecho);
  console.log(`${c.nome} | ${achou} | ${count} | ${bateExato ? "exato" : "DIVERGE"} | ${JSON.stringify(texts.join(" | "))}`);
  document.body.removeChild(container);
  if (!achou || !bateExato) algumaFalha = true;
}

if (algumaFalha) {
  console.error("\nFALHOU: pelo menos um caso não realçou ou o trecho marcado diverge do pedido.");
  process.exit(1);
} else {
  console.log(`\nOK: todos os ${casos.length} casos realçaram o trecho pedido, exatamente (sem contar espaço entre nós).`);
}

// Prova à parte do off-by-one (item MENOR): um caso engenheirado para o corte do laço de
// encurtamento cair exatamente em cima de um espaço. Sem o `while (usados > 0 && alvo[...
// ] === " ") usados--`, o caractere seguinte ao espaço (o "I" de "Iotaaaaa") entrava na marca.
console.log("\n--- off-by-one (prefixo terminando em espaço) ---");
{
  const docOffByOne =
    "Alfaaaaa Betaaaaa Gamaaaaa Deltaaaa Epsilooo Zetaaaaa Etaaaaaa Tetaaaaa Iotaaaaa.";
  const trechoOffByOne = `${docOffByOne}Z`; // "Z" nunca existe no doc -> força o encurtamento
  const container = document.createElement("div");
  container.innerHTML = `<p>${docOffByOne}</p>`;
  document.body.appendChild(container);
  const achou = realcar(container, trechoOffByOne);
  const texto = [...container.querySelectorAll("mark.source-hit")].map((m) => m.textContent).join("");
  document.body.removeChild(container);
  const esperado = "Alfaaaaa Betaaaaa Gamaaaaa Deltaaaa Epsilooo Zetaaaaa Etaaaaaa Tetaaaaa";
  console.log("marcado:", JSON.stringify(texto));
  if (!achou || texto !== esperado) {
    console.error(`FALHOU: esperado ${JSON.stringify(esperado)}, obtido ${JSON.stringify(texto)}.`);
    process.exit(1);
  }
  console.log("OK: parou exatamente no espaço, sem incluir o \"I\" de \"Iotaaaaa\".");
}
