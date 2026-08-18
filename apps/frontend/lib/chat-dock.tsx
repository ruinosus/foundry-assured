"use client";

// Estado do chat lateral — aberto/fechado, compartilhado por todas as telas de gestão.
//
// É contexto e não estado local porque duas coisas distantes precisam dele: o botão no shell
// (que alterna) e o painel na página (que aparece). Passar por props obrigaria cada tela a
// carregar o estado só para repassá-lo.
//
// O padrão vem do `aap-kb` (`lib/chat-dock.tsx`), e o motivo de existir é o mesmo: um campo do
// wizard pode pedir ajuda ao agente, e o pedido precisa ABRIR o chat para a pessoa ver a
// conversa acontecendo. Ajuda que chega sem mostrar de onde veio é ajuda que não se audita.

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface ChatDock {
  open: boolean;
  show: () => void;
  hide: () => void;
  toggle: () => void;
  /** Qual agente atende o dock. Fica AQUI e não no componente porque um campo do wizard precisa
   *  poder trocá-lo: só os domínios montados pelo adapter oficial enxergam a tool `propose_field`
   *  (medido — o caminho grounded não repassa tools do cliente), e pedir ajuda de campo a um
   *  agente que não pode propor produziria uma conversa educada e inútil. */
  agentId: string;
  setAgentId: (id: string) => void;
  /** Manda uma pergunta para o chat: abre o dock, troca de agente se preciso, e enfileira o
   *  texto. Quem consome é a ponte dentro do provider do CopilotKit — este arquivo não fala com
   *  o agente, só carrega a intenção até quem fala. */
  ask: (prompt: string, agent?: string) => void;
  /** O pedido pendente e o reconhecimento de que ele foi entregue. */
  pending: { prompt: string; nonce: number } | null;
  clearPending: () => void;
}

const Ctx = createContext<ChatDock | null>(null);

/** O agente padrão do dock: o BUILDER, que é quem sabe preencher formulário e é o único que pode
 *  chamar `propose_field`. Era `selfwiki`, escolhido quando o dock só respondia perguntas sobre o
 *  produto — e um grounded não consegue propor campo nenhum. */
const AGENTE_PADRAO = "builder";

export function ChatDockProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [agentId, setAgentId] = useState(AGENTE_PADRAO);
  const [pending, setPending] = useState<{ prompt: string; nonce: number } | null>(null);

  const show = useCallback(() => setOpen(true), []);
  const hide = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((v) => !v), []);
  const clearPending = useCallback(() => setPending(null), []);

  const ask = useCallback((prompt: string, agent?: string) => {
    if (agent) setAgentId(agent);
    setOpen(true);
    // `nonce` porque a MESMA pergunta pode ser feita duas vezes seguidas ("melhore de novo"), e
    // sem ele o estado não mudaria e a ponte não dispararia a segunda vez.
    setPending({ prompt, nonce: Date.now() });
  }, []);

  const value = useMemo(
    () => ({ open, show, hide, toggle, agentId, setAgentId, ask, pending, clearPending }),
    [open, show, hide, toggle, agentId, ask, pending, clearPending],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Fora do provider o dock é inerte, em vez de quebrar — uma tela sem chat continua funcionando. */
const NOOP: ChatDock = {
  open: false,
  show: () => {},
  hide: () => {},
  toggle: () => {},
  agentId: AGENTE_PADRAO,
  setAgentId: () => {},
  ask: () => {},
  pending: null,
  clearPending: () => {},
};

export function useChatDock(): ChatDock {
  return useContext(Ctx) ?? NOOP;
}
