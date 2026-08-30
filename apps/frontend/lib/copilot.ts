// O copiloto como a tela o consome — e a matriz de recursos do motor.
//
// A MATRIZ É O CORAÇÃO DESTA TELA, e o desenho dela tem uma regra que se erra com facilidade:
//
//     "não precisa" NÃO é "não cumpre".
//
// Um copiloto de RH não fica pior por não ter trilha encadeada — ele não tem peça probatória a
// sustentar. Por isso a matriz não pontua, não dá nota e não mostra fração: ela separa o que o
// copiloto USA do que ele NÃO PRECISA, com o motivo de cada um. Um painel que dissesse "4 de 11"
// transformaria ausência legítima em dívida, e a primeira reação de quem lê seria declarar
// recursos que o domínio não pede — que é o oposto de um manifesto honesto.

export interface CopilotTarget {
  flow: string;
  writes?: string[];
  validateAgainst?: string;
}

export interface Copilot {
  name: string;
  title?: string;
  description?: string;
  surface?: { mount?: string; screens?: string[]; openByDefault?: boolean };
  engine?: { agent?: string; protocol?: string; runtime?: string; model?: string };
  grounding?: { bases?: string[]; citation?: string; refuseWithoutSource?: boolean };
  targets?: CopilotTarget[];
  tools?: { read?: string[]; write?: { name: string; require_approval?: string; role?: string }[] };
  voice?: { language?: string; declareBeforeActing?: boolean };
  measurement?: { record?: string; outcomes?: string[] };
  policy?: string;
  /** Os problemas dos alvos, calculados pelo backend. Vazio = tudo confere. */
  target_problems?: string[];
}

/** Uma linha da matriz. `usa` decide o LADO, nunca uma nota. */
export interface RecursoDoMotor {
  id: string;
  usa: boolean;
  /** Por que usa, ou por que não precisa — sempre uma frase, nunca um vazio. */
  detalhe: string;
}

/** A matriz, derivada do documento.
 *
 *  Cada linha responde uma pergunta que o manifesto declara. Os textos vêm da tela (traduzidos);
 *  o que este arquivo decide é o LADO e o valor interpolado. */
export function recursosDoMotor(
  c: Copilot,
  t: (k: string, v?: Record<string, string | number>) => string,
): RecursoDoMotor[] {
  const targets = c.targets ?? [];
  const campos = targets.flatMap((x) => x.writes ?? []);
  const escritas = c.tools?.write ?? [];
  const bases = c.grounding?.bases ?? [];
  const telas = c.surface?.screens ?? [];

  return [
    {
      id: "proposta",
      usa: campos.length > 0,
      detalhe: campos.length
        ? t("recurso_proposta_usa", { count: campos.length })
        : t("recurso_proposta_nao"),
    },
    {
      id: "escrita_com_gate",
      usa: escritas.length > 0,
      detalhe: escritas.length
        ? t("recurso_escrita_usa", { list: escritas.map((w) => w.name).join(", ") })
        : t("recurso_escrita_nao"),
    },
    {
      id: "fundamentacao",
      usa: bases.length > 0,
      detalhe: bases.length
        ? t("recurso_base_usa", { list: bases.join(", ") })
        : t("recurso_base_nao"),
    },
    {
      id: "recusa_sem_fonte",
      usa: !!c.grounding?.refuseWithoutSource,
      detalhe: c.grounding?.refuseWithoutSource
        ? t("recurso_recusa_usa")
        : t("recurso_recusa_nao"),
    },
    {
      id: "superficie_declarada",
      usa: telas.length > 0,
      detalhe: telas.length ? t("recurso_telas_usa", { list: telas.join(", ") }) : t("recurso_telas_nao"),
    },
    {
      id: "politica_herdada",
      usa: !!c.policy,
      detalhe: c.policy ? t("recurso_politica_usa", { name: c.policy }) : t("recurso_politica_nao"),
    },
    {
      id: "medicao",
      usa: !!c.measurement?.record,
      detalhe: c.measurement?.record
        ? t("recurso_medicao_usa", { list: (c.measurement.outcomes ?? []).join(", ") })
        : t("recurso_medicao_nao"),
    },
    {
      id: "runtime_declarado",
      usa: !!c.engine?.runtime,
      detalhe: c.engine?.runtime
        ? t("recurso_runtime_usa", { runtime: c.engine.runtime })
        : t("recurso_runtime_nao"),
    },
  ];
}
