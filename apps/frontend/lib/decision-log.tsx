"use client";

// O LOG DE DECISÕES DA SESSÃO — o que esta pessoa decidiu, nesta aba, agora.
//
// POR QUE ELE EXISTE, e por que NÃO é a trilha de auditoria.
//
// A trilha (ADR-023) é a prova: encadeada por hash, ancorada, no servidor, e ela guarda o
// desfecho e a medida — nunca o texto. Ela responde a um auditor, meses depois. Este log responde
// a outra pergunta, de outra pessoa, em outro momento: *"o que eu já decidi nesta sessão?"* —
// feita por quem está no meio de preencher um formulário e recebeu a quarta proposta seguida.
//
// Sem ele, a resposta era a rolagem do chat. Cada proposta aceita vira uma linha `applied` que
// some para cima conforme a conversa segue, e quem quer conferir se já usou a proposta de
// `instructions` precisa rolar procurando um card que já colapsou.
//
// É DELIBERADAMENTE EFÊMERO. Vive em memória, morre com a aba, e não vai para lugar nenhum. Se
// fosse persistido viraria um segundo registro do mesmo fato — e dois registros do mesmo fato
// divergem, com o agravante de que este é o que não tem hash. A trilha continua sendo a única
// coisa que se pode citar; este é um bloco de rascunho.

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

/** O que aconteceu com uma proposta ou com uma ação que esperava aprovação. */
export type DecisionOutcome =
  | "accepted"
  | "edited"
  | "discarded"
  | "approved"
  | "rejected";

export interface Decision {
  id: string;
  /** O campo, ou o nome da ação que esperava aprovação. */
  subject: string;
  outcome: DecisionOutcome;
  /** Hora local, formatada na hora do registro — o log não recalcula nada depois. */
  at: string;
}

interface DecisionLog {
  decisions: Decision[];
  record: (subject: string, outcome: DecisionOutcome) => void;
  clear: () => void;
}

const Ctx = createContext<DecisionLog | null>(null);

/** Teto de linhas. O log é uma ajuda de sessão, não um histórico: sem teto, uma sessão longa
 *  acumularia centenas de linhas num painel de 200px que ninguém rola até o fim. */
const MAX = 50;

export function DecisionLogProvider({ children }: { children: ReactNode }) {
  const [decisions, setDecisions] = useState<Decision[]>([]);

  const record = useCallback((subject: string, outcome: DecisionOutcome) => {
    setDecisions((atual) =>
      [
        {
          id:
            typeof crypto !== "undefined" && crypto.randomUUID
              ? crypto.randomUUID()
              : `${Date.now()}-${atual.length}`,
          subject,
          outcome,
          // `toLocaleTimeString` sem locale fixo: a hora segue o aparelho de quem decide, que é
          // quem vai ler. Formatada AGORA e guardada como string — um timestamp reformatado a
          // cada render mudaria de fuso se a pessoa trocasse a língua no meio da sessão.
          at: new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }),
        },
        ...atual,
      ].slice(0, MAX),
    );
  }, []);

  const clear = useCallback(() => setDecisions([]), []);

  const value = useMemo(() => ({ decisions, record, clear }), [decisions, record, clear]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Fora do provider o log é inerte — uma tela sem dock continua funcionando, e registrar uma
 *  decisão nunca pode ser o que quebra a decisão. */
const NOOP: DecisionLog = { decisions: [], record: () => {}, clear: () => {} };

export function useDecisionLog(): DecisionLog {
  return useContext(Ctx) ?? NOOP;
}
