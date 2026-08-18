// A transcrição de uma conversa virando eventos de AG-UI — a metade PURA da reidratação.
//
// O PROBLEMA, que o dna-cloud documentou antes de nós: o runner padrão do CopilotKit responde o
// `agent/connect` SÓ da memória do processo. Ele nunca consulta o armazenamento durável onde a
// transcrição de fato vive. Depois de um restart do servidor, de uma réplica nova ou de uma
// sessão nova, o connect transmite NADA — e a conversa parece vazia até o próximo envio, cuja
// resposta replica o histórico. É exatamente o "o histórico só aparece depois que você manda uma
// mensagem".
//
// A nossa versão anterior disso era o `ThreadSeeder`: um componente que buscava as mensagens e
// chamava `setMessages` na tela. Funcionava e estava no lugar errado — a reidratação passava a
// depender de o painel de conversas estar montado, e qualquer outro caminho que abrisse uma
// conversa começava vazio.
//
// Separado do route porque é lógica pura: sem rxjs, sem runtime, testável direto.

export type ThreadHistory = { agent: string; messages: unknown[] };

/** Os eventos que reproduzem uma transcrição num `connect`. Lista vazia quando não há
 *  mensagens — e vazio aqui significa "nada a replicar", que renderiza a tela de boas-vindas.
 *  Nunca se fabrica um evento para preencher silêncio. */
export function historyConnectEvents(threadId: string, messages: unknown[]): unknown[] {
  if (!messages.length) return [];
  const runId = `history-${threadId}`;
  return [
    { type: "RUN_STARTED", threadId, runId },
    { type: "MESSAGES_SNAPSHOT", messages },
    { type: "RUN_FINISHED", threadId, runId },
  ];
}

/** As mensagens gravadas de uma conversa, do nosso backend.
 *
 *  DEGRADA PARA VAZIO em qualquer falha — backend fora, resposta não-OK, corpo ilegível. O
 *  connect então replica nada e a tela se comporta como antes desta função existir. O erro é
 *  registrado no servidor; nada fabricado aparece como real. */
export async function fetchThreadHistory(
  baseUrl: string,
  threadId: string,
  headers: Record<string, string>,
  fetchImpl: typeof fetch = fetch,
): Promise<ThreadHistory> {
  const base = baseUrl.replace(/\/+$/, "");
  try {
    const r = await fetchImpl(`${base}/conversations/by-id/${encodeURIComponent(threadId)}`, {
      cache: "no-store",
      headers,
    });
    if (!r.ok) return { agent: "", messages: [] };
    const body = (await r.json()) as { agent?: string; messages?: unknown[] };
    return { agent: body.agent ?? "", messages: Array.isArray(body.messages) ? body.messages : [] };
  } catch (erro) {
    console.error("[thread-history] não foi possível ler a conversa", threadId, erro);
    return { agent: "", messages: [] };
  }
}

/** As mensagens gravadas, no formato que o AG-UI espera.
 *
 *  Os dois caminhos de gravação produzem formas diferentes — o `HistoryProvider` guarda
 *  `Message.to_dict()` (com `contents`), o caminho grounded guarda `{role, text}`. Normalizar
 *  aqui é o que permite reidratar uma conversa sem saber por qual caminho ela foi escrita. */
export function toAguiMessages(gravadas: unknown[], threadId: string): unknown[] {
  const saida: unknown[] = [];
  gravadas.forEach((bruta, i) => {
    const m = bruta as { role?: string; text?: string; contents?: { text?: string }[] };
    const texto =
      m.text || (m.contents ?? []).map((c) => c?.text).filter(Boolean).join("\n") || "";
    if (!texto) return;
    saida.push({
      id: `${threadId}-${i}`,
      role: m.role === "assistant" ? "assistant" : "user",
      content: texto,
    });
  });
  return saida;
}
