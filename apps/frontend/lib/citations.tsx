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
          else pendente.current = citations;
        } else if (event?.type === "TEXT_MESSAGE_START") {
          const esperando = pendente.current;
          const id = event?.messageId ?? event?.message_id;
          if (esperando && id) {
            pendente.current = null;
            setPorMensagem((m) => ({ ...m, [id]: esperando }));
          }
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
