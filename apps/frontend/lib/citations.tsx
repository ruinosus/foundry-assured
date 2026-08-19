"use client";

// A EVIDÊNCIA É DA MENSAGEM, não da sessão.
//
// Antes daqui o painel guardava um array só e o RUN_STARTED o limpava a cada turno: rolar a
// conversa para cima mostrava respostas antigas sem fonte nenhuma. A causa raiz estava no
// backend — o evento não dizia a qual resposta pertencia (ver Task 1).
//
// DUAS REGRAS DE LIGAÇÃO, e as duas são necessárias:
//   · evento COM message_id  → liga direto (caminho grounded: emitido depois do texto)
//   · evento SEM message_id  → fica pendente e liga na PRÓXIMA mensagem que começa
//     (caminho de workflow: o executor emite entre o retrieve e o resolve, então a próxima
//      mensagem É o resolve — a ordem é o que torna a regra determinística)
//
// A pendência (`pendente.current`, note bem: NÃO o `porMensagem` acima) só vale DENTRO do run
// que a emitiu — por isso é limpa em RUN_STARTED (não herdar de um run anterior) e em
// RUN_FINISHED/RUN_ERROR (não vazar para o próximo, quando o run termina sem mensagem nova:
// erro, interrupt antes do resolve, resolve sem texto). Sem isso, fonte errada colada numa
// afirmação de OUTRA pergunta é falha silenciosa e mais grave que fonte ausente.

import { useAgent } from "@copilotkit/react-core/v2";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

export interface Citation {
  type?: "citation";
  title: string;
  url?: string;
  snippet?: string;
  index: number;
}

const Ctx = createContext<Record<string, Citation[]>>({});

// Aceita a forma nova {message_id, citations}, a antiga (array solto) e o vocabulário anterior
// ({source, content}). Uma aba aberta durante o deploy continua recebendo o formato antigo.
function normalizar(value: unknown): { messageId: string | null; citations: Citation[] } {
  const bruto = Array.isArray(value)
    ? { message_id: null, citations: value }
    : ((value ?? {}) as { message_id?: string | null; citations?: unknown[] });
  const lista = (bruto.citations ?? []) as (Citation & { source?: string; content?: string })[];
  return {
    messageId: bruto.message_id ?? null,
    citations: lista.map((c) => ({
      index: c.index,
      title: c.title ?? c.source ?? "",
      url: c.url,
      snippet: c.snippet ?? c.content,
    })),
  };
}

export function CitationsProvider({ agentId, children }: { agentId: string; children: ReactNode }) {
  const { agent } = useAgent({ agentId });
  const [porMensagem, setPorMensagem] = useState<Record<string, Citation[]>>({});
  // `ref` e não `state`: a pendência é lida dentro do próprio handler de evento, e um state
  // capturado no closure daria o valor do render anterior.
  const pendente = useRef<Citation[] | null>(null);

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      onEvent: ({ event }: any) => {
        if (event?.type === "CUSTOM" && event?.name === "sources") {
          const { messageId, citations } = normalizar(event.value);
          if (!citations.length) return;
          if (messageId) setPorMensagem((m) => ({ ...m, [messageId]: citations }));
          // CONCATENA em vez de sobrescrever: pode haver mais de um evento sem message_id no
          // mesmo run (ex.: dois lotes de fontes entre o retrieve e o resolve). Sobrescrever
          // silenciosamente descartava o primeiro.
          else pendente.current = [...(pendente.current ?? []), ...citations];
        } else if (event?.type === "TEXT_MESSAGE_START") {
          const esperando = pendente.current;
          const id = event?.messageId ?? event?.message_id;
          if (esperando && id) {
            pendente.current = null;
            setPorMensagem((m) => ({ ...m, [id]: esperando }));
          }
        } else if (
          event?.type === "RUN_STARTED" ||
          event?.type === "RUN_FINISHED" ||
          event?.type === "RUN_ERROR"
        ) {
          // A pendência só vale DENTRO do run que a emitiu. Sem isto, um run que termina sem
          // mensagem nova (erro, interrupt antes do resolve, resolve sem texto) deixa
          // `pendente.current` vivo indefinidamente — e a PRÓXIMA mensagem que começar a
          // receber, mesmo em outra pergunta, outra thread ou depois do toggle Live/Hosted,
          // herda uma citação que não é dela. Fonte errada colada numa afirmação é pior que
          // fonte ausente, e é silenciosa: por isso limpa tanto no início (não herdar de um run
          // anterior) quanto no fim (não vazar para o próximo).
          pendente.current = null;
        }
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  return <Ctx.Provider value={porMensagem}>{children}</Ctx.Provider>;
}

export function useCitationsFor(messageId: string | undefined): Citation[] {
  const mapa = useContext(Ctx);
  return (messageId && mapa[messageId]) || [];
}
