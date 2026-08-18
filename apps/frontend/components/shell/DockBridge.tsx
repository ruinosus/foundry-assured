"use client";

// A ponte entre uma TELA e o agente do dock.
//
// Um campo do wizard não fala com o agente: ele chama `ask()` no contexto do dock, que abre o
// painel e enfileira o pedido. Quem entrega é este componente, porque só ele está dentro do
// provider do CopilotKit — e a separação é o que permite ao campo ser um componente burro, sem
// depender de estar montado dentro de provider nenhum.
//
// POR QUE O PEDIDO VAI PARA O CHAT, e não para um endpoint dedicado. É o padrão do `aap-kb` e do
// `dna-cloud`, e o motivo é auditoria antes de estética: a pessoa VÊ o pedido acontecendo, vê a
// resposta chegar, e a proposta entra no campo por um gesto dela. Uma sugestão que aparece do
// nada não tem de onde vir — e "ajuda que chega sem mostrar de onde veio é ajuda que não se
// audita" já estava escrito no contexto do dock antes de existir motivo para usá-la.

import { useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { useEffect, useRef } from "react";
import { useChatDock } from "@/lib/chat-dock";

export function DockBridge() {
  const { agentId, open, pending, clearPending } = useChatDock();
  const { agent, isReady } = useAgent({ agentId });
  const { copilotkit } = useCopilotKit();
  // O nonce já entregue. Sem isto um re-render reenviaria o mesmo pedido, e o agente responderia
  // duas vezes à mesma pergunta.
  const entregue = useRef<number>(0);

  useEffect(() => {
    // ESPERA O DOCK ABRIR. O `ChatDock` devolve null enquanto fechado, então o `<CopilotChat>` —
    // que assina o agente e renderiza as mensagens — só monta depois.
    if (!open || !isReady || !pending || pending.nonce === entregue.current) return;
    entregue.current = pending.nonce;

    let vivo = true;
    const prompt = pending.prompt;
    clearPending();

    // O CAMINHO É O MESMO DO COMPOSER do CopilotKit, verificado no bundle:
    //
    //     agent.addMessage({id, role:"user", content}) ;  await copilotkit.runAgent({agent})
    //
    // O que faltava era ESPERAR e TRATAR. `void runAgent(...)` engolia a rejeição, e quando ela
    // acontecia — o agente ainda não terminou de sincronizar com o runtime no primeiro clique — a
    // mensagem ficava na tela sem resposta, exatamente como "enviei e não aconteceu nada". O
    // segundo clique funcionava porque a sincronização já havia terminado.
    const enviar = async (tentativa: number): Promise<void> => {
      if (!vivo) return;
      try {
        if (tentativa === 0) {
          const id =
            typeof crypto !== "undefined" && crypto.randomUUID
              ? crypto.randomUUID()
              : `${Date.now()}`;
          agent.addMessage({ id, role: "user", content: prompt });
        }
        await copilotkit.runAgent({ agent });
      } catch (erro) {
        // Três tentativas com espera crescente. Um agente que nunca sincroniza é problema de
        // conexão, e aí o erro precisa APARECER — silêncio aqui foi o que custou duas rodadas de
        // depuração.
        if (tentativa < 2 && vivo) {
          await new Promise((r) => setTimeout(r, 150 * (tentativa + 1)));
          return enviar(tentativa + 1);
        }
        console.error("[DockBridge] não foi possível rodar o agente", erro);
      }
    };

    void enviar(0);
    return () => {
      vivo = false;
    };
  }, [agent, isReady, open, pending, clearPending, copilotkit]);

  return null;
}
