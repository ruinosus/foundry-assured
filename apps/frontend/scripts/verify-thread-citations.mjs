#!/usr/bin/env node
// Prova que a reidratação de uma conversa antiga (`historyConnectEvents`, lib/thread-history.ts)
// devolve a citação junto do texto — o sintoma que este trabalho existe para corrigir era
// "reabrir a conversa mostra a resposta sem fonte nenhuma".
//
// Não é parte dos gates de CI por acaso — é o padrão de `verify-highlight.mjs`: importa as
// funções DE VERDADE (transpiladas na hora, sem bundler) e afirma sobre o retorno delas. Uma
// prova que reimplementasse `idDaMensagem`/`historyCitationEvents` aqui dentro passaria com o
// MESMO bug que a revisão apontou (os dois lados batendo por sorte, não por desenho) — por isso
// nada disto é recopiado.
//
//   node scripts/verify-thread-citations.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const srcPath = path.join(here, "..", "lib", "thread-history.ts");
const src = readFileSync(srcPath, "utf8");

const { outputText } = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "thread-history.ts",
});

const mod = { exports: {} };
new Function("module", "exports", "require", outputText)(mod, mod.exports, () => {});
const { historyCitationEvents, toAguiMessages, historyConnectEvents } = mod.exports;

let algumaFalha = false;
function checar(nome, condicao) {
  console.log(`${condicao ? "OK" : "FALHOU"}: ${nome}`);
  if (!condicao) algumaFalha = true;
}

// O id que `toAguiMessages` atribui à mensagem de índice `i`, lido do RESULTADO da função — não
// recalculado. É contra ELE que os `message_id` dos eventos de citação são comparados.
function idAtribuido(mensagensAgui, indiceOriginal, gravadas) {
  // `toAguiMessages` pula mensagem sem texto, então o índice na saída não é o índice na entrada.
  // Reconstrói a correspondência andando pelas duas listas na mesma ordem — sem reimplementar a
  // fórmula do id, só usando o texto como âncora para achar QUAL saída veio de QUAL entrada.
  let vistos = 0;
  for (let i = 0; i <= indiceOriginal; i++) {
    const bruta = gravadas[i];
    const texto = bruta.text || (bruta.contents ?? []).map((c) => c?.text).filter(Boolean).join("\n") || "";
    if (!texto) continue;
    if (i === indiceOriginal) return mensagensAgui[vistos].id;
    vistos++;
  }
  return undefined;
}

// --- Caso 1: conversa gravada com annotations produz evento `sources` com o id certo ---
{
  const threadId = "thread-abc";
  const gravadas = [
    { role: "user", text: "como reinicio o servico X?" },
    {
      role: "assistant",
      text: "reinicie pelo painel.",
      annotations: [{ title: "runbook-x.md", index: 0, snippet: "reinicie pelo painel" }],
    },
  ];
  const mensagens = toAguiMessages(gravadas, threadId);
  const eventos = historyCitationEvents(threadId, gravadas);
  const idEsperado = idAtribuido(mensagens, 1, gravadas);

  checar("uma mensagem com annotations produz exatamente um evento sources", eventos.length === 1);
  checar(
    "o evento tem message_id igual ao id que toAguiMessages atribuiu à mesma mensagem",
    eventos[0]?.type === "CUSTOM" &&
      eventos[0]?.name === "sources" &&
      eventos[0]?.value?.message_id === idEsperado &&
      idEsperado !== undefined,
  );
  checar(
    "a citação viaja intacta no evento",
    JSON.stringify(eventos[0]?.value?.citations) === JSON.stringify(gravadas[1].annotations),
  );
}

// --- Caso 2: mensagem sem annotations não produz evento ---
{
  const threadId = "thread-sem-fonte";
  const gravadas = [
    { role: "user", text: "oi" },
    { role: "assistant", text: "ola, como posso ajudar?" },
  ];
  const eventos = historyCitationEvents(threadId, gravadas);
  checar("mensagem do assistente sem annotations não produz evento", eventos.length === 0);
}

// --- Caso 3: mensagem de usuário com annotations (não deveria existir, mas por via das
//     dúvidas) não produz evento — só o ASSISTENTE cita fonte ---
{
  const threadId = "thread-usuario-com-annotations";
  const gravadas = [{ role: "user", text: "pergunta", annotations: [{ title: "x", index: 0 }] }];
  const eventos = historyCitationEvents(threadId, gravadas);
  checar("mensagem de usuário não produz evento mesmo com annotations", eventos.length === 0);
}

// --- Caso 4: o caso que hoje funciona por SORTE — mensagem vazia no meio não desalinha os ids ---
// `toAguiMessages` pula mensagem sem texto DEPOIS de capturar o índice `i` do forEach. Se
// `historyCitationEvents` usasse um índice contado à parte (ex.: o comprimento do array de
// saída), o id que ela calcula divergiria do id real assim que houvesse uma mensagem vazia
// antes da que carrega a citação. Este caso tem uma mensagem vazia bem no meio, exatamente para
// pegar essa divergência se ela existir.
{
  const threadId = "thread-com-buraco";
  const gravadas = [
    { role: "user", text: "pergunta 1" },
    { role: "assistant", text: "resposta 1, sem fonte" },
    { role: "assistant", text: "" }, // mensagem vazia: toAguiMessages pula, sem emitir id pra ela
    { role: "user", text: "pergunta 2" },
    {
      role: "assistant",
      text: "resposta 2, com fonte",
      annotations: [{ title: "runbook-y.md", index: 0, snippet: "resposta 2" }],
    },
  ];
  const mensagens = toAguiMessages(gravadas, threadId);
  const eventos = historyCitationEvents(threadId, gravadas);
  const idEsperado = idAtribuido(mensagens, 4, gravadas);

  checar("mensagem vazia no meio não é convertida (toAguiMessages pula)", mensagens.length === 4);
  checar(
    "mesmo com o buraco, o evento de citação aponta pro id real da mensagem 4",
    eventos.length === 1 && eventos[0]?.value?.message_id === idEsperado && idEsperado !== undefined,
  );
}

// --- Caso 5: historyConnectEvents intercala RUN_STARTED, MESSAGES_SNAPSHOT, sources*, RUN_FINISHED ---
{
  const threadId = "thread-connect";
  const gravadas = [
    { role: "user", text: "pergunta" },
    {
      role: "assistant",
      text: "resposta com fonte",
      annotations: [{ title: "runbook-z.md", index: 0, snippet: "resposta" }],
    },
  ];
  const eventos = historyConnectEvents(threadId, gravadas);
  const tipos = eventos.map((e) => `${e.type}${e.type === "CUSTOM" ? `:${e.name}` : ""}`);
  checar(
    "a ordem é RUN_STARTED, MESSAGES_SNAPSHOT, CUSTOM:sources, RUN_FINISHED",
    JSON.stringify(tipos) === JSON.stringify(["RUN_STARTED", "MESSAGES_SNAPSHOT", "CUSTOM:sources", "RUN_FINISHED"]),
  );
  const snapshot = eventos.find((e) => e.type === "MESSAGES_SNAPSHOT");
  const sources = eventos.find((e) => e.type === "CUSTOM" && e.name === "sources");
  checar(
    "o message_id do evento sources bate com o id da mensagem no MESSAGES_SNAPSHOT",
    snapshot?.messages?.[1]?.id === sources?.value?.message_id,
  );
}

if (algumaFalha) {
  console.error("\nFALHOU: pelo menos uma checagem de citação de histórico não passou.");
  process.exit(1);
} else {
  console.log("\nOK: reabrir uma conversa gravada com citações reproduz os eventos sources corretos.");
}
