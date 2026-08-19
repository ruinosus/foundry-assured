"use client";

// A evidência DA RESPOSTA, logo abaixo dela — e o [n] do texto levando até ela.
//
// Confirmar evidência é ver a fonte junto da afirmação, não num painel que já trocou de
// conteúdo. Antes daqui o painel lateral guardava só o último turno; rolar a conversa para
// cima mostrava respostas sem fonte.
//
// USA OS SLOTS CANÔNICOS do CopilotKit v2 — `assistantMessage` e, dentro dele,
// `markdownRenderer`. Nada de renderizador de chat próprio (MÁXIMA MAIOR). O renderizador
// padrão continua fazendo TODO o trabalho de markdown, para o CONTEÚDO INTEIRO, numa ÚNICA
// chamada — a primeira versão fazia `content.split(/(\[\d{1,3}\])/g)` e renderizava cada pedaço
// num `MarkdownRenderer` independente, o que quebra qualquer markdown que atravesse uma
// fronteira de pedaço (tabela com `[n]` numa célula, bloco cercado partido ao meio, lista
// virando N `<ol>`) e ainda transformava `[n]` de CÓDIGO (`argv[1]`, `A[1]` de Mermaid) em botão.
// A troca do marcador por botão agora é um `rehypePlugin` (`lib/rehype-citations.ts`) que mexe
// só em nós de TEXTO da árvore já parseada, pulando `code`/`pre` — o `MarkdownRenderer` aceita
// todas as props do Streamdown por baixo (conferido em `node_modules/@copilotkit/react-core/
// dist/copilotkit-D0aAnD3i.d.mts`: `Omit<ComponentProps<typeof Streamdown>, "children">`).
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
import { useMemo } from "react";
import { defaultRehypePlugins, type StreamdownProps } from "streamdown";
import { useCitationsFor } from "@/lib/citations";
import { rehypeCitations } from "@/lib/rehype-citations";

// `streamdown` depende de `unified@11` numa cópia PRÓPRIA (`node_modules/streamdown/node_modules/
// unified`), diferente da que fica hoisted no topo do projeto (`unified@10`, trazida por outra
// dependência) — os dois `Pluggable`/`PluggableList` não são o MESMO tipo estrutural (`unified@11`
// tirou a variante `Preset` da união). Importar `PluggableList` do pacote `unified` direto pega a
// cópia errada e não bate com o que `rehypePlugins` do Streamdown espera. Derivar o tipo do
// PRÓPRIO `StreamdownProps` (que a `MarkdownRenderer` do CopilotKit repassa) usa sempre a versão
// que o Streamdown realmente lê, sem precisar declarar `unified` como dependência à parte.
type RehypePlugins = NonNullable<StreamdownProps["rehypePlugins"]>;

function abrirFonte(domainId: string, name: string, snippet?: string) {
  // O TRECHO VIAJA JUNTO porque é ele que o visualizador destaca. Sem ele o documento abre
  // inteiro e a pessoa caça em 9KB — que é o problema que este trabalho existe para resolver.
  window.dispatchEvent(new CustomEvent("abrir-fonte", { detail: { domainId, name, snippet } }));
}

// O elemento `<data>` que `rehypeCitations` injeta na árvore vira este botão. Índice órfão (o
// modelo escreveu [13] com 12 documentos) nunca chega aqui — `rehypeCitations` já deixa esse
// caso como texto simples, então este componente só existe para citação válida.
function BotaoCitacao({
  domainId,
  openLabel,
  ...props
}: {
  domainId: string;
  openLabel: string;
  "data-citation-index"?: number;
  "data-citation-title"?: string;
  "data-citation-snippet"?: string;
  children?: React.ReactNode;
}) {
  const indice = props["data-citation-index"];
  const titulo = props["data-citation-title"] ?? "";
  const snippet = props["data-citation-snippet"] || undefined;
  return (
    <button
      type="button"
      className="cit-ref"
      title={titulo}
      aria-label={`${openLabel}: ${titulo}`}
      onClick={() => abrirFonte(domainId, titulo, snippet)}
    >
      [{indice}]
    </button>
  );
}

export function makeAssistantMessage(domainId: string): typeof CopilotChatAssistantMessage {
  function AssistantMessageComEvidencia(props: CopilotChatAssistantMessageProps) {
    const te = useTranslations("evidence");
    const citations = useCitationsFor(props.message.id);
    const openLabel = te("openSource");

    // Roda DEPOIS dos plugins padrão do Streamdown (raw → katex → sanitize → harden, nessa
    // ordem — conferido em `node_modules/streamdown/dist/chunk-JAPRZBRM.js`, `Wo`/`Ko`): o nó
    // `<data>` que injetamos é sintético, não veio do markdown do usuário, então não há por que
    // o sanitizer da lib decidir que `data-citation-*` é atributo desconhecido e descartá-lo.
    // Tupla `[attacher, options]`, não a chamada já feita — é assim que o `unified` (que o
    // Streamdown usa por baixo) invoca um plugin com opções; passar a função já invocada faz o
    // `unified` chamá-la de novo, agora como se ELA fosse o attacher, com `tree` indefinido.
    const rehypePlugins = useMemo(
      () => [...Object.values(defaultRehypePlugins), [rehypeCitations, citations]] as RehypePlugins,
      [citations],
    );
    const components = useMemo(
      () => ({
        // `any`: o `.d.ts` do React não tem índice para `data-*` arbitrário (só conhece os
        // atributos padrão de `<data>`), então não existe tipo estrutural correto para o que o
        // `rehypeCitations` injeta. Mesma lacuna do cast documentado no fim do arquivo — não é
        // uma aposta nova, é o valor real batendo numa borda que o `.d.ts` não modela.
        data: (p: any) => <BotaoCitacao domainId={domainId} openLabel={openLabel} {...p} />,
      }),
      // `domainId` é valor de escopo externo (parâmetro de `makeAssistantMessage`, fixo por
      // instância deste componente) — o eslint recusa como dependência porque mutá-lo não
      // re-renderiza nada aqui.
      [openLabel],
    );

    // IMPORTANT 1 (re-revisão): esta arrow PRECISA ser memoizada — mas com dependência nos
    // valores DERIVADOS das citações (`rehypePlugins`/`components`), nunca com array vazio nem
    // sem `useMemo` nenhum. As duas formas óbvias quebram, cada uma de um jeito:
    //
    //   · Arrow INLINE (sem memo) — a versão anterior, e o achado "óbvio" desta re-revisão: o
    //     `markdownRenderer` remonta a subárvore markdown a CADA re-render da mensagem, inclusive
    //     a cada token durante o streaming e em TODAS as mensagens do thread sempre que o mapa de
    //     citações muda (é o "Mermaid re-renderizando" que o IMPORTANT 3 desta mesma tarefa disse
    //     ter eliminado, uma camada abaixo — aqui ele reaparece).
    //
    //   · Arrow memoizada com dependência ESTÁVEL (`useCallback(..., [])` ou equivalente) —
    //     conserto "óbvio" e ERRADO: medido que o `memo` do `Streamdown` (`chunk-JAPRZBRM.js`)
    //     IGNORA `rehypePlugins`/`components` no comparador — só olha `children`/`shikiTheme`/
    //     `isAnimating`/`mode`. No caminho grounded o evento `sources` chega DEPOIS do
    //     `TextMessageEndEvent` (`grounded.py:247`/`:264`): quando a citação chega, `content` (que
    //     é `children` lá dentro) já é o mesmo de antes. Se a IDENTIDADE do `markdownRenderer`
    //     também não mudar, o Streamdown faz bail-out por `children` igual e o `[n]` NUNCA vira
    //     botão nesse caminho — falha SILENCIOSA, sem erro nenhum. Quem "limpar" a dependência
    //     achando redundante reintroduz exatamente este bug.
    //
    // O meio-termo: dependência em `[rehypePlugins, components]`, os dois já memoizados acima com
    // dependência real (`[citations]` e `[openLabel]`). Identidade muda SÓ quando a citação muda
    // — remonta uma vez (o que o Streamdown exige pra reprocessar o `[n]`) e para de remontar a
    // cada token. Isto por sua vez depende do `useCitationsFor` devolver referência ESTÁVEL para
    // "sem citação" (Minor 1, `lib/citations.tsx`) — sem aquilo, toda mensagem sem citação teria
    // `citations` novo a cada render e a cadeia de memoização inteira não travaria em nada.
    const markdownRenderer = useMemo(() => {
      // Função NOMEADA, não arrow anônima: `react/display-name` (eslint) acusa componente sem
      // nome quando devolvido de dentro de outra função — nome próprio resolve o lint sem mudar
      // comportamento nenhum.
      function ComCitacoes({ content }: { content: string }) {
        return (
          <CopilotChatAssistantMessage.MarkdownRenderer
            content={content}
            rehypePlugins={rehypePlugins}
            components={components}
          />
        );
      }
      return ComCitacoes;
    }, [rehypePlugins, components]);

    return (
      <>
        <CopilotChatAssistantMessage {...props} markdownRenderer={markdownRenderer} />
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
  // medido; não inventa comportamento novo. `as unknown as` porque o valor passa a AFIRMAR ter
  // `.MarkdownRenderer` e os outros estáticos, o que um cast direto esconderia — a lacuna fica
  // visível em vez de disfarçada.
  return AssistantMessageComEvidencia as unknown as typeof CopilotChatAssistantMessage;
}
