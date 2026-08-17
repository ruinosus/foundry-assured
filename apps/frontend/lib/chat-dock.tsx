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
}

const Ctx = createContext<ChatDock | null>(null);

export function ChatDockProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const show = useCallback(() => setOpen(true), []);
  const hide = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((v) => !v), []);
  const value = useMemo(() => ({ open, show, hide, toggle }), [open, show, hide, toggle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Fora do provider o dock é inerte, em vez de quebrar — uma tela sem chat continua funcionando. */
const NOOP: ChatDock = { open: false, show: () => {}, hide: () => {}, toggle: () => {} };

export function useChatDock(): ChatDock {
  return useContext(Ctx) ?? NOOP;
}
