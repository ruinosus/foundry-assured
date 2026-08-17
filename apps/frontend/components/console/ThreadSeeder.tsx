"use client";

// Põe as mensagens de uma conversa antiga DE VOLTA na tela.
//
// Trocar o `threadId` faz o backend continuar a conversa certa — o `HistoryProvider` carrega o
// histórico no contexto do agente. Mas a TELA continuaria vazia: o CopilotKit não busca
// transcrição do nosso store, ele só busca da nuvem dele (que não usamos, ver ConversationsPanel).
//
// Então quem semeia somos nós: `useAgent()` devolve o `AbstractAgent` do AG-UI, que expõe
// `setMessages()`. É a mesma superfície que o próprio CopilotKit usa — não é gambiarra, é o ponto
// de entrada público do agente.
//
// Precisa viver DENTRO do `<CopilotKitProvider>`: `useAgent` lê o contexto do provider e lança
// fora dele.

import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useRef } from "react";
import { authedFetch } from "@/lib/auth/api";

type Stored = { role?: string; text?: string; contents?: { text?: string }[] };

/** O texto de uma mensagem gravada, venha ela do agent-framework (`contents`) ou do caminho
 *  grounded (`text` direto). Os dois formatos convivem porque os domínios gravam por caminhos
 *  diferentes — ver `conversations/internal/listing.record_turn`. */
function texto(m: Stored): string {
  if (m.text) return m.text;
  for (const parte of m.contents ?? []) {
    if (parte?.text) return parte.text;
  }
  return "";
}

export function ThreadSeeder({
  agentId,
  agentKey,
  threadId,
}: {
  agentId: string;
  agentKey: string;
  threadId: string;
}) {
  // `useAgent({ agentId })` — a variante COMPARTILHADA, de propósito. O tipo do pacote admite
  // exatamente duas formas, e a outra (`{agentId, runtimeAgentId, threadId}`) registra um agente
  // PRIVADO, que seria uma segunda instância: as mensagens iriam para um agente que o
  // `<CopilotChat>` não renderiza. Aqui o thread vem da configuração do chat — que é justamente
  // a prop `threadId` que o console já passa —, então este hook e o chat falam do mesmo agente.
  const { agent, isReady } = useAgent({ agentId });
  // Semeia UMA vez por conversa. Sem isto, cada re-render reescreveria as mensagens e apagaria o
  // que o usuário acabou de digitar.
  const semeado = useRef<string>("");

  useEffect(() => {
    if (!isReady || !threadId || semeado.current === threadId) return;
    let vivo = true;

    (async () => {
      try {
        const r = await authedFetch(
          `/api/conversations/${encodeURIComponent(agentKey)}/${encodeURIComponent(threadId)}`,
          { cache: "no-store" },
        );
        if (!vivo) return;
        // 404 é o caso normal de conversa NOVA. Não há o que semear — mas há o que LIMPAR: o
        // agente é compartilhado e ainda segura as mensagens da conversa anterior. Sem esta
        // linha, "+ Nova" trocava o threadId e deixava a tela cheia do papo antigo, e os prompts
        // sugeridos (que só aparecem com a conversa vazia) nunca mais voltavam.
        if (!r.ok) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any -- ver nota abaixo
          (agent as any).setMessages?.([]);
          semeado.current = threadId;
          return;
        }
        const body = await r.json().catch(() => ({}));
        const mensagens = (body.messages ?? []) as Stored[];
        const mapeadas = mensagens
          .map((m, i) => ({
            id: `${threadId}-${i}`,
            role: (m.role === "assistant" ? "assistant" : "user") as "assistant" | "user",
            content: texto(m),
          }))
          .filter((m) => m.content);

        if (vivo) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any -- setMessages aceita o
          // Message do AG-UI; o tipo exportado é um union grande de Zod e não vale importá-lo só
          // para dois campos.
          (agent as any).setMessages?.(mapeadas);
        }
        semeado.current = threadId;
      } catch {
        // Falhar em semear deixa a tela vazia, e o backend ainda tem o histórico: o usuário
        // continua a conversa sem ver o passado. Ruim, mas melhor que quebrar a página.
        semeado.current = threadId;
      }
    })();

    return () => {
      vivo = false;
    };
  }, [agent, isReady, threadId, agentKey]);

  return null;
}
