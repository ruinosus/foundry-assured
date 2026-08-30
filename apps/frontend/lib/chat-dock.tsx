"use client";

// Estado do chat lateral — aberto/fechado, compartilhado por todas as telas de gestão.
//
// É contexto e não estado local porque duas coisas distantes precisam dele: o botão no shell
// (que alterna) e o painel na página (que aparece). Passar por props obrigaria cada tela a
// carregar o estado só para repassá-lo.
//
// O padrão vem de um projeto anterior (`lib/chat-dock.tsx`), e o motivo de existir é o mesmo: um campo do
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
  /** O campo do formulário que pediu a última proposta.
   *
   *  Vive aqui, e não no campo, porque a pergunta que ele responde é do DOCK: "para qual campo eu
   *  vou escrever?". Pedir "melhore" em dois campos seguidos produzia duas propostas e nenhuma
   *  pista de qual veio de onde — e o card de proposta aparece no chat, longe do campo. */
  focusedField: string | null;
  setFocusedField: (field: string | null) => void;
}

const Ctx = createContext<ChatDock | null>(null);

/** O agente padrão do dock: o BUILDER, que é quem sabe preencher formulário e é o único que pode
 *  chamar `propose_field`. Era `selfwiki`, escolhido quando o dock só respondia perguntas sobre o
 *  produto — e um grounded não consegue propor campo nenhum. */
const AGENTE_PADRAO = "builder";

export function ChatDockProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [agentId, setAgentId] = useState(AGENTE_PADRAO);
  const [focusedField, setFocusedField] = useState<string | null>(null);
  const show = useCallback(() => setOpen(true), []);
  const hide = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((v) => !v), []);
  const value = useMemo(
    () => ({ open, show, hide, toggle, agentId, setAgentId, focusedField, setFocusedField }),
    [open, show, hide, toggle, agentId, focusedField],
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
  focusedField: null,
  setFocusedField: () => {},
};

export function useChatDock(): ChatDock {
  return useContext(Ctx) ?? NOOP;
}
