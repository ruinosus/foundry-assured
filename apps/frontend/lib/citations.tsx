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

// MESMO merge para os dois ramos (com e sem `message_id`), com dedupe por `index`. Antes disso o
// ramo com `message_id` SOBRESCREVIA (`{...m, [messageId]: citations}`) e o ramo sem `message_id`
// CONCATENAVA sem checar duplicata — dois eventos `sources` idênticos no mesmo run (reconexão de
// SSE, replay) duplicavam a lista ("Fontes (6)" com cada documento duas vezes), e dois eventos
// com o MESMO `message_id` faziam o segundo descartar o primeiro em silêncio — o mesmo bug que já
// foi corrigido do outro lado. Último valor por índice vence (não faz diferença para eventos
// idênticos; para eventos divergentes é a leitura mais recente da fonte).
function mesclarCitacoes(existentes: Citation[] | undefined | null, novas: Citation[]): Citation[] {
  const porIndice = new Map((existentes ?? []).map((c) => [c.index, c]));
  for (const c of novas) porIndice.set(c.index, c);
  // Ordenado por índice: um segundo evento com índice menor que o primeiro (ordem de chegada
  // não é ordem de citação) produziria "3, 4, 1, 2" na lista sem isto.
  return [...porIndice.values()].sort((a, b) => a.index - b.index);
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
          // Os dois ramos usam o MESMO merge com dedupe por índice (`mesclarCitacoes`) — ver
          // comentário da função. Antes só o ramo sem `message_id` concatenava; o outro
          // sobrescrevia direto.
          if (messageId) {
            setPorMensagem((m) => ({ ...m, [messageId]: mesclarCitacoes(m[messageId], citations) }));
          } else {
            pendente.current = mesclarCitacoes(pendente.current, citations);
          }
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
    return () => {
      sub.unsubscribe();
      // IMPORTANT 2 (re-revisão): o efeito depende só de `[agent]`, e o `ref` pertence à
      // INSTÂNCIA DO PROVIDER — trocar de agente (toggle Live/Hosted) não remonta o provider, só
      // troca a prop. Sequência do bug: run em andamento emite `sources` sem `message_id` →
      // usuário troca de agente → `agentId` muda → ESTE cleanup roda (unsubscribe) ANTES de
      // assinar o novo agente → o `RUN_FINISHED` daquele run nunca chega a ser visto (a
      // assinatura que o veria já foi cancelada) → o handler de RUN_FINISHED acima, que limpa
      // `pendente.current`, nunca dispara → a pendência sobrevive na ref → a PRÓXIMA mensagem, já
      // no OUTRO agente, herda uma citação que não é dela. Por isso a limpeza tem que estar aqui
      // também, não só reagindo a eventos do próprio agente: ao desligar desta assinatura, o run
      // que ela estava seguindo deixou de poder ser concluído por ela.
      pendente.current = null;
    };
  }, [agent]);

  return <Ctx.Provider value={porMensagem}>{children}</Ctx.Provider>;
}

// Constante de módulo, não `[]` literal a cada chamada: um array novo por render invalidaria
// qualquer `useMemo`/`useCallback` que dependa do RESULTADO desta função para mensagens sem
// citação (é o caso de `MessageEvidence.tsx` — ver comentário do IMPORTANT 1 lá). `[] !== []`
// para `Object.is`, então sem isto a "mensagem sem citação" nunca estabiliza.
const VAZIO: Citation[] = [];

export function useCitationsFor(messageId: string | undefined): Citation[] {
  const mapa = useContext(Ctx);
  return (messageId && mapa[messageId]) || VAZIO;
}
