"use client";

// Campo com ações de IA — a versão que fala com o CHAT.
//
// SUBSTITUI O `AssistedField`, e a diferença não é de fachada. O `AssistedField` chamava um
// endpoint dedicado e trazia a sugestão de volta abaixo do campo: funcionava, e criava um SEGUNDO
// caminho de escrita, com o próprio prompt em Python. Este manda o pedido ao chat, e quem escreve
// é o agente publicado (`builder`) chamando a tool `propose_field`.
//
// Três coisas melhoram de uma vez:
//
//   1. a pessoa VÊ o pedido acontecendo e a resposta chegando — a proposta tem de onde vir;
//   2. dá para ITERAR ("agora mais curto", "cita a base X"), porque é uma conversa e não um
//      botão que devolve um texto final;
//   3. o agente pode declarar a FONTE do que escreveu, e a fonte é registrada (ADR-023).
//
// As ações mudam com o estado do campo, porque a pergunta muda: campo vazio pede "escrever",
// campo cheio pede "melhorar". Oferecer as duas sempre faria metade dos botões não fazer sentido.
//
// `onPrompt` ausente = o campo renderiza SEM as ações, em vez de com botões mortos.

import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { useChatDock } from "@/lib/chat-dock";

/** O agente que atende o wizard. Fixo aqui e não escolhido pela pessoa: só ele sabe preencher
 *  formulário E consegue chamar a tool de proposta (os domínios grounded não recebem tools do
 *  cliente — medido). Deixar a escolha aberta produziria uma conversa educada e inútil. */
const AGENTE = "builder";

export function AiField({
  field,
  label,
  value,
  resource,
  children,
}: {
  /** O identificador do campo — é ele que o agente devolve na tool, e é como a proposta
   *  encontra o campo de volta. */
  field: string;
  /** O rótulo humano, já traduzido: viaja dentro do prompt para o agente saber do que se trata. */
  label: string;
  value: string;
  /** Que recurso está sendo criado (agente, base, skill) — muda o que faz sentido propor. */
  resource: string;
  children: ReactNode;
}) {
  const t = useTranslations("aiField");
  const { ask } = useChatDock();
  const [instrucao, setInstrucao] = useState<string | null>(null);

  const preenchido = value.trim().length > 0;

  const pedir = (texto: string) => {
    ask(texto, AGENTE);
    setInstrucao(null);
  };

  return (
    <div className="ai-field">
      {/* As ações ficam ESCONDIDAS até o hover ou o foco, como no `aap-kb`. O motivo não é
          estético: um formulário com um botão de IA ao lado de cada campo vira uma tela de
          botões de IA, e a pessoa passa a escolher entre eles em vez de preencher. Aparecendo no
          campo em que ela já está, a ajuda chega no momento certo e some no resto do tempo.

          `opacity` + `pointer-events`, nunca `display: none`: escondido por display sai da ordem
          de tabulação, e a ajuda deixaria de existir para quem navega por teclado. Com
          `:focus-within`, tabular até o botão o revela. */}
      <div className="ai-field-actions" aria-label={t("actionsFor", { field: label })}>
        {preenchido ? (
          <button
            type="button"
            className="ai-chip"
            title={t("revise")}
            onClick={() =>
              pedir(
                t("revisePrompt", {
                  field,
                  label,
                  resource,
                  value: value.slice(0, 2000),
                }),
              )
            }
          >
            <span aria-hidden>✎</span> {t("revise")}
          </button>
        ) : (
          <button
            type="button"
            className="ai-chip"
            title={t("generate")}
            onClick={() => pedir(t("generatePrompt", { field, label, resource }))}
          >
            <span aria-hidden>✨</span> {t("generate")}
          </button>
        )}
        <button
          type="button"
          className="ai-chip ai-chip-icon"
          title={t("custom")}
          aria-label={t("custom")}
          onClick={() => setInstrucao(instrucao === null ? "" : null)}
        >
          <span aria-hidden>💬</span>
        </button>
      </div>
      {children}

      {instrucao !== null && (
        <div className="row-tight">
          <input
            className="acct-btn"
            value={instrucao}
            placeholder={t("customPlaceholder")}
            onChange={(e) => setInstrucao(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && instrucao.trim()) {
                pedir(t("customPrompt", { field, label, resource, instruction: instrucao.trim() }));
              }
            }}
          />
          <button
            type="button"
            className="acct-btn t-xs"
            disabled={!instrucao.trim()}
            onClick={() =>
              pedir(t("customPrompt", { field, label, resource, instruction: instrucao.trim() }))
            }
          >
            {t("send")}
          </button>
        </div>
      )}
    </div>
  );
}
