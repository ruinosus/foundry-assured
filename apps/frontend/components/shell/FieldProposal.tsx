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
import { authedFetch } from "@/lib/auth/api";
import { diffWords } from "@/lib/text-diff";
import { useDecisionLog } from "@/lib/decision-log";
import { z } from "zod";

/** O antes → depois do campo.
 *
 *  POR QUE ELE É A PEÇA CENTRAL DO CARD. Sem comparação, decidir sobre uma proposta exige manter
 *  na cabeça o que já estava escrito — e num campo de instruções de nove linhas ninguém mantém.
 *  O resultado prático era aceitar por confiança, que é o oposto do que o gate existe para
 *  produzir.
 *
 *  Campo vazio NÃO ganha um diff onde tudo é verde: ele ganha uma frase dizendo que não há o que
 *  comparar. Um bloco inteiro marcado como adição parece uma mudança grande quando é só o
 *  primeiro preenchimento. */
function Diff({ antes, depois }: { antes: string; depois: string }) {
  const t = useTranslations("fieldProposal");
  const vazio = antes.trim().length === 0;
  const r = vazio ? null : diffWords(antes, depois);

  if (vazio) {
    return (
      <div className="proposal-diff">
        <p className="t-2xs muted-line proposal-diff-empty">{t("noPrevious")}</p>
        <pre className="doc-preview">{depois}</pre>
      </div>
    );
  }

  // Acima do teto o diff não é calculado (ver lib/text-diff.ts). Mostrar os dois textos inteiros
  // é pior que o diff e melhor que uma comparação que trava a aba — e o motivo é DITO.
  if (r!.truncated) {
    return (
      <div className="proposal-diff">
        <p className="t-2xs muted-line">{t("diffTooLong")}</p>
        <pre className="doc-preview">{depois}</pre>
      </div>
    );
  }

  return (
    <div className="proposal-diff">
      <p className="t-2xs muted-line">{t("beforeAfter")}</p>
      <pre className="doc-preview proposal-diff-body">
        {r!.parts.map((p, i) =>
          p.op === "same" ? (
            <span key={i}>{p.text}</span>
          ) : (
            <span key={i} className={p.op === "add" ? "diff-add" : "diff-del"}>
              {p.text}
            </span>
          ),
        )}
      </pre>
      <p className="t-2xs muted-line">
        {t("diffSummary", { added: r!.added, removed: r!.removed, from: antes.length, to: depois.length })}
      </p>
    </div>
  );
}

/** Registra o DESFECHO da proposta. Silencioso de propósito: é medição, e uma falha de medição
 *  não pode impedir alguém de usar ou descartar o texto. O que se perde é uma linha de
 *  estatística; o que se ganharia bloqueando é nada. */
function registrar(
  resource: string,
  field: string,
  outcome: "accepted" | "edited" | "discarded",
  sources: string[],
  chars: number,
) {
  void authedFetch("/api/builder-assist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resource, field, outcome, sources, chars }),
  }).catch(() => {});
}

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
  valorAtual,
  fontes,
  motivo,
  conhecido,
  recurso,
  validar,
  onAccept,
}: {
  campo: string;
  recurso: string;
  valorProposto: string;
  /** O que está no campo AGORA — o lado esquerdo do diff. */
  valorAtual: string;
  fontes: string[];
  motivo: string;
  conhecido: boolean;
  /** A mesma regra que o formulário aplica ao campo. Devolve o motivo, ou null. */
  validar?: (campo: string, valor: string) => string | null;
  onAccept: (p: FieldProposal) => void;
}) {
  const t = useTranslations("fieldProposal");
  // O log da SESSÃO, ao lado do registro no servidor. São dois destinatários diferentes: o
  // servidor mede aproveitamento ao longo do tempo; este responde "o que eu já decidi agora?".
  const { record } = useDecisionLog();
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

  // A PROPOSTA É VALIDADA ANTES DE VIRAR DECISÃO. A regra é a do formulário — a mesma função,
  // não uma cópia —, e ela roda sobre o texto EDITADO quando há edição. Antes disto, um `name`
  // com maiúsculas proposto pelo agente era aceito no card e só reprovava na publicação, três
  // telas depois do erro. Erro que chega longe de onde foi causado é o pior tipo.
  const problema = validar ? validar(campo, texto) : null;

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
        <Diff antes={valorAtual} depois={texto} />
      )}

      {problema && (
        <p className="t-xs bad-line" role="status">
          {t("invalid", { reason: problema })}
        </p>
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
          próprio conhecimento é honesto —, mas a tela distingue os dois casos.

          As fontes viram FICHAS em vez de uma lista separada por vírgula dentro de uma linha
          cinza. É o que sustenta o campo: com peso de texto auxiliar, ela era lida como rodapé.
          A ficha NÃO é um link: o agente do formulário não consulta documento nenhum (ver
          `builder.py` — nenhuma tool de servidor), então o que ele declara é o nome da base que
          ele diz ter usado, e não há documento para abrir. Um link que resolve em 404 seria pior
          que o texto cinza que havia antes. */}
      {fontes.length ? (
        <div className="proposal-sources">
          <span className="t-2xs muted-line">{t("sourcesLabel")}</span>
          <ul className="source-chips">
            {fontes.map((f) => (
              <li key={f} className="source-chip" title={f}>
                {f}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="t-xs muted-line">{t("noSources")}</p>
      )}

      <div className="row-tight">
        <button
          type="button"
          className="btn btn-approve"
          disabled={problema !== null}
          title={problema ?? undefined}
          onClick={() => {
            onAccept({ field: campo, value: texto, sources: fontes });
            // ACEITA vs EDITADA são desfechos diferentes, e a diferença é o sinal de qualidade:
            // um assistente muito aceito e muito editado está sendo tolerado, não usado.
            registrar(recurso, campo, editando ? "edited" : "accepted", fontes, texto.length);
            record(campo, editando ? "edited" : "accepted");
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
        <button
          type="button"
          className="btn"
          onClick={() => {
            registrar(recurso, campo, "discarded", fontes, valorProposto.length);
            record(campo, "discarded");
            setUsado(true);
          }}
        >
          {t("discard")}
        </button>
      </div>
    </div>
  );
}

export function FieldProposalTool({
  onAccept,
  fields,
  resource = "",
  current,
  validate,
}: {
  onAccept: (proposal: FieldProposal) => void;
  /** Que recurso o formulário cria — entra na medição para separar wizard de agente, de skill e
   *  de base. */
  resource?: string;
  /** Os campos que ESTE formulário tem. Proposta para campo inexistente é dita, não engolida. */
  fields: string[];
  /** O valor ATUAL de cada campo, para o diff. Ausente ⇒ o card mostra só o texto proposto, que é
   *  o comportamento anterior — nenhum formulário quebra por não passar isto. */
  current?: Record<string, string>;
  /** A regra do campo, para validar a proposta ANTES de ela virar decisão. O formulário passa a
   *  mesma função que ele já usa, e não uma cópia: duas regras divergem, e a que diverge em
   *  silêncio é a do card. */
  validate?: (field: string, value: string) => string | null;
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
        valorAtual={current?.[String(args?.field ?? "")] ?? ""}
        motivo={String(args?.reason ?? "")}
        fontes={Array.isArray(args?.sources) ? (args.sources as string[]).map(String) : []}
        conhecido={fields.includes(String(args?.field ?? ""))}
        recurso={resource}
        validar={validate}
        onAccept={onAccept}
      />
    ),
  });

  return null;
}
