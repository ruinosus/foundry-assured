"use client";

// A tool `propose_field` — como o agente propõe um campo, e por que ela RESPONDE NA HORA.
//
// A PRIMEIRA VERSÃO USAVA `useHumanInTheLoop` e QUEBRAVA. Ela deixa a chamada PENDENTE até a
// pessoa decidir, e o caminho do Foundry é stateful: a requisição seguinte levava uma chamada de
// função sem resultado, e o serviço recusava com
//
//     400 — No tool output found for function call call_…
//
// A correção não é técnica, é de semântica. O trabalho do agente é PROPOR; se a pessoa aceita ou
// não, não é assunto do turno dele. Então a tool responde imediatamente ("proposta entregue"), o
// modelo segue em frente, e o CARD continua na tela esperando a decisão humana. O valor entra no
// campo por um gesto da pessoa exatamente como antes — o que mudou é que o MODELO não fica preso
// esperando por ele.
//
// Isso preserva a propriedade que importa (nada é escrito sem gesto humano) e elimina a pendência
// que o protocolo não suporta.

import { useFrontendTool } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { z } from "zod";

export type FieldProposal = {
  field: string;
  value: string;
  sources: string[];
};

/** O card. Componente próprio porque ele tem ESTADO (o texto em edição) — e um render inline não
 *  poderia ter, já que o CopilotKit o remonta a cada atualização do stream. */
function ProposalCard({
  campo,
  valorProposto,
  fontes,
  motivo,
  conhecido,
  onAccept,
}: {
  campo: string;
  valorProposto: string;
  fontes: string[];
  motivo: string;
  conhecido: boolean;
  onAccept: (p: FieldProposal) => void;
}) {
  const t = useTranslations("fieldProposal");
  // A CORREÇÃO só existe enquanto se edita. `useState(valorProposto)` capturava o valor do
  // PRIMEIRO render — e os argumentos da tool chegam em STREAMING, então o primeiro render tem
  // `value` vazio. O card ficava com a caixa em branco para sempre, mesmo depois de o texto
  // inteiro chegar. Derivar do prop enquanto não se edita resolve sem perder a edição.
  const [correcao, setCorrecao] = useState<string | null>(null);
  const [usado, setUsado] = useState(false);
  const editando = correcao !== null;
  const texto = editando ? correcao : valorProposto;

  if (!conhecido) {
    return (
      <div className="notice notice-block">
        <p className="notice-body">{t("unknownField", { field: campo })}</p>
      </div>
    );
  }

  if (usado) {
    return <div className="t-xs ok-line">{t("applied", { field: campo })}</div>;
  }

  return (
    <div className="proposal">
      <span className="approval-eyebrow">{t("title", { field: campo })}</span>

      {editando ? (
        <textarea
          className="acct-btn proposal-edit"
          rows={8}
          value={texto}
          onChange={(e) => setCorrecao(e.target.value)}
        />
      ) : (
        <pre className="doc-preview">{texto}</pre>
      )}

      {/* O PORQUÊ, marcado como o que é: texto do modelo, não fato. Mesma regra do card de
          aprovação — exibido igual ao conteúdo, ele viraria uma segunda afirmação com ar de dado
          e a pessoa aceitaria PELA justificativa em vez de pelo texto. */}
      {motivo && (
        <p className="approval-reason">
          <span className="approval-reason-tag">{t("modelSaid")}</span>
          <span className="t-sm proposal-reason-text">{motivo}</span>
        </p>
      )}

      {/* A PROCEDÊNCIA, antes do aceite. Sem fonte não é erro — o prompt diz que escrever do
          próprio conhecimento é honesto —, mas a tela distingue os dois casos. */}
      <p className="t-xs muted-line">
        {fontes.length ? t("sources", { list: fontes.join(", ") }) : t("noSources")}
      </p>

      <div className="row-tight">
        <button
          type="button"
          className="btn btn-approve"
          onClick={() => {
            onAccept({ field: campo, value: texto, sources: fontes });
            setUsado(true);
          }}
        >
          {editando ? t("acceptEdited") : t("accept")}
        </button>
        {/* EDITAR existe pelo mesmo motivo do card de escalação: aceitar um texto quase certo,
            porque descartar era a única alternativa, não é revisão. */}
        <button
          type="button"
          className="btn"
          onClick={() => setCorrecao(editando ? null : valorProposto)}
        >
          {editando ? t("cancelEdit") : t("edit")}
        </button>
        <button type="button" className="btn" onClick={() => setUsado(true)}>
          {t("discard")}
        </button>
      </div>
    </div>
  );
}

export function FieldProposalTool({
  onAccept,
  fields,
}: {
  onAccept: (proposal: FieldProposal) => void;
  /** Os campos que ESTE formulário tem. Proposta para campo inexistente é dita, não engolida. */
  fields: string[];
}) {
  useFrontendTool({
    name: "propose_field",
    description: "Propose the text of one form field. Returns immediately; the human decides separately whether to use it.", // @texto-para-modelo
    parameters: z.object({
      field: z.string().describe("The field identifier this proposal is for."), // @texto-para-modelo
      value: z.string().describe("The proposed text."), // @texto-para-modelo
      reason: z
        .string()
        .default("")
        .describe("One sentence on WHY you wrote it this way — read by the person before they use it."), // @texto-para-modelo
      sources: z
        .array(z.string())
        .default([])
        .describe(
          "Where the text came from: knowledge base, document or agent names ACTUALLY consulted. Empty when written from your own knowledge — an empty list is honest, an invented name is not.",
        ), // @texto-para-modelo
    }),
    // Responde NA HORA. O retorno é o que o modelo lê para saber que entregou — não é a decisão
    // da pessoa, que acontece depois e não volta para ele.
    handler: async ({ field }) =>
      fields.includes(String(field))
        ? "Proposal shown to the user. Do not repeat the value in your reply." // @texto-para-modelo
        : `Unknown field "${field}". Valid fields: ${fields.join(", ")}.`, // @texto-para-modelo
    render: ({ args }) => (
      <ProposalCard
        campo={String(args?.field ?? "")}
        valorProposto={String(args?.value ?? "")}
        motivo={String(args?.reason ?? "")}
        fontes={Array.isArray(args?.sources) ? (args.sources as string[]).map(String) : []}
        conhecido={fields.includes(String(args?.field ?? ""))}
        onAccept={onAccept}
      />
    ),
  });

  return null;
}
