"use client";

// Abre o dock e manda um prompt para o agente. Chamado DIRETO no clique.
//
// POR QUE DIRETO, e não por uma ponte com estado. A primeira versão punha o pedido num contexto e
// um componente separado o entregava dentro de um `useEffect`. Isso trouxe três bugs em sequência,
// todos de ORDEM: o efeito rodava antes de o chat montar; a rejeição do run era engolida; e a
// limpeza do efeito cancelava o próprio envio que ela deveria proteger.
//
// O `aap-kb` — que faz isto há mais tempo e funciona — não tem ponte: o hook chama `useAgent` no
// componente que clica e envia no manipulador. Sem efeito, sem estado intermediário, sem ordem
// para acertar. É a mesma API que o composer do CopilotKit usa por dentro (verificado no bundle):
//
//     agent.addMessage({id, role: "user", content});  copilotkit.runAgent({agent})
//
// O agente é FIXO no parâmetro, não o que estiver selecionado no dock: só o `builder` sabe
// preencher formulário e chamar `propose_field`, e mandar o pedido para um grounded produziria
// uma conversa educada e inútil.

import { useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { useChatDock } from "@/lib/chat-dock";

export function useSendToDock(agentId: string): (prompt: string) => void {
  const { copilotkit } = useCopilotKit();
  const { agent } = useAgent({ agentId });
  const { show, setAgentId } = useChatDock();

  return (prompt: string) => {
    setAgentId(agentId);
    show();
    agent.addMessage({
      id:
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}`,
      role: "user",
      content: prompt,
    });
    // O erro vai para o console identificado. O composer do CopilotKit faz o mesmo — e foi o
    // silêncio aqui que escondeu a causa por duas rodadas.
    copilotkit
      .runAgent({ agent })
      .catch((erro: unknown) => console.error("[send-to-dock] runAgent falhou", erro));
  };
}
