"use client";

// A evidência DA RESPOSTA, logo abaixo dela — e o [n] do texto levando até ela.
//
// Confirmar evidência é ver a fonte junto da afirmação, não num painel que já trocou de
// conteúdo. Antes daqui o painel lateral guardava só o último turno; rolar a conversa para
// cima mostrava respostas sem fonte.
//
// USA OS SLOTS CANÔNICOS do CopilotKit v2 — `assistantMessage` e, dentro dele,
// `markdownRenderer`. Nada de renderizador de chat próprio (MÁXIMA MAIOR). O renderizador
// padrão continua fazendo todo o trabalho de markdown; nós só trocamos o `[n]` por um botão.
//
// A lista de fontes entra como IRMÃ do `<CopilotChatAssistantMessage>`, não como `children` dele.
// O tipo real do slot (conferido em `node_modules/@copilotkit/react-core/dist/copilotkit-
// D0aAnD3i.d.mts`, `WithSlots`) define `children` como uma FUNÇÃO que recebe os elementos JÁ
// RENDERIZADOS (markdownRenderer/toolbar/toolCallsView…) e assume sozinha a marcação inteira do
// balão — não o `ReactNode` solto que a primeira leitura do plano sugeria. Reconstruir aquela
// marcação aqui duplicaria detalhe interno do pacote que pode mudar em versão futura. Um
// Fragment com o componente padrão e a lista de fontes ao lado entrega o mesmo resultado visual
// sem essa duplicação.

import {
  CopilotChatAssistantMessage,
  type CopilotChatAssistantMessageProps,
} from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { Fragment } from "react";
import { useCitationsFor, type Citation } from "@/lib/citations";

function abrirFonte(domainId: string, name: string, snippet?: string) {
  // O TRECHO VIAJA JUNTO porque é ele que o visualizador destaca. Sem ele o documento abre
  // inteiro e a pessoa caça em 9KB — que é o problema que este trabalho existe para resolver.
  window.dispatchEvent(new CustomEvent("abrir-fonte", { detail: { domainId, name, snippet } }));
}

// Troca `[n]` por um botão quando existe citação n. Índice órfão (o modelo escreveu [13] com
// 12 documentos) fica TEXTO SIMPLES — um link que não leva a lugar nenhum é pior que nenhum.
function ComMarcadores({
  content,
  citations,
  domainId,
  openLabel,
}: {
  content: string;
  citations: Citation[];
  domainId: string;
  openLabel: string;
}) {
  const porIndice = new Map(citations.map((c) => [c.index, c]));
  const partes = content.split(/(\[\d{1,3}\])/g);
  return (
    <>
      {partes.map((parte, i) => {
        const m = /^\[(\d{1,3})\]$/.exec(parte);
        const cit = m ? porIndice.get(Number(m[1])) : undefined;
        if (!cit) {
          return (
            <Fragment key={i}>
              <CopilotChatAssistantMessage.MarkdownRenderer content={parte} />
            </Fragment>
          );
        }
        return (
          <button
            key={i}
            type="button"
            className="cit-ref"
            title={cit.title}
            aria-label={`${openLabel}: ${cit.title}`}
            onClick={() => abrirFonte(domainId, cit.title, cit.snippet)}
          >
            [{cit.index}]
          </button>
        );
      })}
    </>
  );
}

export function makeAssistantMessage(domainId: string): typeof CopilotChatAssistantMessage {
  function AssistantMessageComEvidencia(props: CopilotChatAssistantMessageProps) {
    const te = useTranslations("evidence");
    const citations = useCitationsFor(props.message.id);
    const openLabel = te("openSource");

    return (
      <>
        <CopilotChatAssistantMessage
          {...props}
          markdownRenderer={({ content }: { content: string }) =>
            citations.length ? (
              <ComMarcadores
                content={content}
                citations={citations}
                domainId={domainId}
                openLabel={openLabel}
              />
            ) : (
              <CopilotChatAssistantMessage.MarkdownRenderer content={content} />
            )
          }
        />
        {citations.length > 0 && (
          <div className="msg-evidence">
            <div className="msg-evidence-title">
              {te("sources")} ({citations.length})
            </div>
            <ol className="msg-evidence-list">
              {citations.map((c) => (
                <li key={c.index}>
                  <button
                    type="button"
                    className="msg-evidence-item"
                    onClick={() => abrirFonte(domainId, c.title, c.snippet)}
                  >
                    <span className="cit-idx" aria-hidden>
                      {c.index}
                    </span>
                    <span className="cit-title">{c.title}</span>
                    <span className="cit-open" aria-hidden>
                      ↗
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        )}
      </>
    );
  }
  // O TIPO REAL do slot (`SlotValue<typeof CopilotChatAssistantMessage>`, em
  // `copilotkit-D0aAnD3i.d.mts`) inclui, na variante "componente", os membros ESTÁTICOS do
  // namespace (`MarkdownRenderer`, `Toolbar`, `CopyButton`…) — o `.d.mts` funde função + namespace
  // num tipo só. Em TEMPO DE EXECUÇÃO (conferido em `copilotkit-DMmUbvpo.mjs`,
  // `renderSlotElement`/`isReactComponentType`) o único teste é `typeof slot === "function"`,
  // seguido de `React.createElement(slot, props)` — os estáticos nunca são lidos quando o slot é
  // um componente próprio. O cast documenta essa lacuna entre o `.d.ts` e o comportamento real
  // medido; não inventa comportamento novo.
  return AssistantMessageComEvidencia as typeof CopilotChatAssistantMessage;
}
