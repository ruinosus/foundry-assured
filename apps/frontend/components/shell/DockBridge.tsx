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
    // que é quem assina o agente e renderiza as mensagens — só monta depois. Entregar antes disso
    // fazia o primeiro clique rodar o agente com ninguém escutando: a resposta acontecia e não
    // aparecia, e a pessoa clicava de novo. O segundo clique "funcionava" porque o chat já estava
    // montado — sintoma clássico de corrida que parece intermitência.
    if (!open || !isReady || !pending || pending.nonce === entregue.current) return;
    entregue.current = pending.nonce;

    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}`;
    agent.addMessage({ id, role: "user", content: pending.prompt });

    // Roda pelo CORE, não pelo agente. Medido, e foi o defeito: quem monta a lista de tools do
    // frontend é o core —
    //
    //     core.runAgent({agent})  →  tools: this.buildFrontendTools(agent.agentId)  →  agent.runAgent(input)
    //
    // Chamar `agent.runAgent()` direto pula essa montagem e a requisição sai com `tools: []`. O
    // sintoma no chat era o modelo IMITANDO a chamada em texto: ele fora instruído a usar
    // `propose_field`, a ferramenta nunca chegou, e ele escreveu o que teria chamado.
    void copilotkit.runAgent({ agent });
    clearPending();
  }, [agent, isReady, open, pending, clearPending, copilotkit]);

  return null;
}
