"use client";

// A tool `propose_field` — como o agente escreve num campo, e por que ele não escreve direto.
//
// `useHumanInTheLoop` é a primitiva do CopilotKit para tool SEM handler: o agente chama, a tela
// renderiza, e a decisão da PESSOA resolve a chamada. É a peça certa aqui porque a propriedade
// que precisamos é exatamente essa — o valor entra no campo por um gesto humano, nunca por
// retorno de função.
//
// A ALTERNATIVA que não foi feita: dar ao agente uma tool com handler que preenche o campo. Ela
// funcionaria e apagaria a revisão — o agente passaria a escrever no formulário, e o "aceitar"
// viraria um desfazer. Proposta e escrita são coisas diferentes; a ADR-022 diz isso para recurso,
// e vale igual para campo.
//
// AS FONTES são parte do contrato da tool, não enfeite. O prompt do `builder` exige `sources` em
// toda proposta, e o card as MOSTRA — se o agente escreveu com base numa base de conhecimento, a
// pessoa vê qual antes de aceitar. Aceitar registra a procedência (ADR-023): a auditoria ponta a
// ponta que o dono do projeto pediu começa aqui, no momento em que um texto de origem conhecida
// entra num recurso que será publicado.

import { useHumanInTheLoop } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { z } from "zod";

export type FieldProposal = {
  field: string;
  value: string;
  sources: string[];
};

export function FieldProposalTool({
  onAccept,
  fields,
}: {
  /** Chamado quando a pessoa aceita. Recebe a proposta INTEIRA, com as fontes, porque quem
   *  publica precisa gravar a procedência junto. */
  onAccept: (proposal: FieldProposal) => void;
  /** Os campos que ESTE formulário tem. Uma proposta para campo que não existe é recusada com
   *  motivo, em vez de sumir — o agente precisa saber que errou o nome. */
  fields: string[];
}) {
  const t = useTranslations("fieldProposal");

  useHumanInTheLoop({
    name: "propose_field",
    // A descrição vai para o MODELO — é ela que faz o agente chamar a tool em vez de responder
    // o texto no chat.
    description: "Propose the text of one form field. The human accepts or discards; nothing is written directly.", // @texto-para-modelo
    // Zod porque o CopilotKit aceita "any Standard Schema V1 compatible library" e o zod v4 é
    // uma — JSON Schema cru não é aceito aqui (o tipo recusa). As descrições vão para o modelo:
    // são elas que fazem `sources` ser preenchido com o que foi consultado, e não com um nome
    // plausível.
    parameters: z.object({
      field: z.string().describe("The field identifier this proposal is for."), // @texto-para-modelo
      value: z.string().describe("The proposed text."), // @texto-para-modelo
      sources: z
        .array(z.string())
        .default([])
        .describe(
          "Where the text came from: knowledge base, document or agent names ACTUALLY consulted. Empty when written from the model's own knowledge — an empty list is honest, an invented name is not.",
        ),
    }),
    render: ({ args, status, respond }) => {
      const campo = String(args?.field ?? "");
      const valor = String(args?.value ?? "");
      const fontes = Array.isArray(args?.sources) ? (args.sources as string[]).map(String) : [];

      if (status !== "executing" || !respond) {
        return <div className="t-xs muted-line">{t("done", { field: campo })}</div>;
      }

      // Campo que não existe neste formulário: recusa COM MOTIVO. Ignorar em silêncio faria o
      // agente repetir o mesmo erro, e a pessoa esperar por uma proposta que nunca chega.
      if (campo && !fields.includes(campo)) {
        return (
          <div className="notice notice-block">
            <p className="notice-body">{t("unknownField", { field: campo })}</p>
            <button
              type="button"
              className="btn"
              onClick={() => respond({ accepted: false, reason: `unknown field: ${campo}` })}
            >
              {t("dismiss")}
            </button>
          </div>
        );
      }

      return (
        <div className="proposal">
          <span className="approval-eyebrow">{t("title", { field: campo })}</span>
          <pre className="doc-preview">{valor}</pre>

          {/* A PROCEDÊNCIA, visível antes do aceite. Sem fonte declarada não é erro — o prompt
              diz que escrever do próprio conhecimento é honesto —, mas a tela distingue os dois
              casos, porque "veio da base X" e "veio do modelo" pesam diferente. */}
          <p className="t-xs muted-line">
            {fontes.length ? t("sources", { list: fontes.join(", ") }) : t("noSources")}
          </p>

          <div className="row-tight">
            <button
              type="button"
              className="btn btn-approve"
              onClick={() => {
                onAccept({ field: campo, value: valor, sources: fontes });
                respond({ accepted: true });
              }}
            >
              {t("accept")}
            </button>
            <button
              type="button"
              className="btn"
              // O motivo volta para o AGENTE, para ele saber que não foi erro dele.
              onClick={() => respond({ accepted: false, reason: "discarded by the user" })} // @texto-para-modelo
            >
              {t("discard")}
            </button>
          </div>
        </div>
      );
    },
  });

  return null;
}
