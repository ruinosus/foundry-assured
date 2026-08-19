"use client";

// O documento INTEIRO que sustenta a citação — porque ver um nome de arquivo não confirma nada.
//
// O DESTAQUE É MELHOR-ESFORÇO, de propósito: o trecho vem do ÍNDICE e o documento vem do BLOB,
// então eles podem divergir por normalização de espaço em branco. Não achou ⇒ mostra o
// documento sem destaque. Falhar a visualização por causa do realce seria trocar a
// funcionalidade por um enfeite.
//
// Escuta um evento de `window` em vez de receber props: quem dispara é um botão dentro do
// renderizador de mensagem do CopilotKit, que não tem como alcançar este componente pela
// árvore de React. É o mesmo caminho que o MermaidZoom ao lado já usa.

import { CopilotChatAssistantMessage } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { realcar } from "@/lib/source-highlight";

interface Aberto {
  domainId: string;
  name: string;
  snippet?: string;
}

export function SourceViewer() {
  const te = useTranslations("evidence");
  const [aberto, setAberto] = useState<Aberto | null>(null);
  const [estado, setEstado] = useState<"carregando" | "ok" | "401" | "403" | "404" | "erro">(
    "carregando",
  );
  const [conteudo, setConteudo] = useState("");
  // Truncagem DECLARADA, nunca silenciosa: quem abriu a citação está prestes a confirmar
  // evidência, e confirmar sobre um documento cortado sem saber é pior do que não ver o final.
  const [truncado, setTruncado] = useState(false);
  const corpo = useRef<HTMLDivElement>(null);
  const fecharBtn = useRef<HTMLButtonElement>(null);
  // Quem tinha o foco antes de abrir — normalmente o botão [n] da citação, fora da árvore de
  // React deste componente. Fechar devolve o foco para lá em vez de deixá-lo perdido no chat.
  const gatilho = useRef<HTMLElement | null>(null);

  const fechar = useCallback(() => {
    setAberto(null);
    gatilho.current?.focus();
    gatilho.current = null;
  }, []);

  useEffect(() => {
    const ao = (e: Event) => {
      gatilho.current = document.activeElement as HTMLElement | null;
      // Reseta ESTADO E CONTEÚDO aqui, no próprio listener — não no efeito de fetch. O
      // listener roda fora do ciclo de eventos do React (evento nativo de `window`), então os
      // efeitos passivos podem só ser liberados DEPOIS de uma pintura: sem isto, reabrir com um
      // documento novo pinta o cabeçalho do documento B em cima do corpo ainda com o markdown
      // do documento A.
      setEstado("carregando");
      setConteudo("");
      setTruncado(false);
      setAberto((e as CustomEvent).detail as Aberto);
    };
    window.addEventListener("abrir-fonte", ao);
    return () => window.removeEventListener("abrir-fonte", ao);
  }, []);

  // Escape fecha, mesmo precedente do DomainPicker.
  useEffect(() => {
    if (!aberto) return;
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") fechar();
    };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [aberto, fechar]);

  // Move o foco para dentro do painel ao abrir (ou trocar de documento com o painel já aberto).
  // Sem isto, quem ativou o [n] pelo teclado fica com o foco no meio da conversa.
  useEffect(() => {
    if (aberto) fecharBtn.current?.focus();
  }, [aberto]);

  useEffect(() => {
    if (!aberto) return;
    let cancelado = false;
    authedFetch(`/api/source/${encodeURIComponent(aberto.domainId)}/${encodeURIComponent(aberto.name)}`)
      .then(async (r) => {
        if (cancelado) return;
        if (r.status === 401) return setEstado("401");
        if (r.status === 403) return setEstado("403");
        if (r.status === 404) return setEstado("404");
        if (!r.ok) return setEstado("erro");
        const body = await r.json();
        setConteudo(String(body?.content ?? ""));
        setTruncado(Boolean(body?.truncated));
        setEstado("ok");
      })
      .catch(() => !cancelado && setEstado("erro"));
    return () => {
      cancelado = true;
    };
  }, [aberto]);

  // Roda DEPOIS da pintura, porque precisa dos nós que o renderizador criou. Falhar em achar
  // o trecho é normal e silencioso: o documento continua aberto e navegável, que é o essencial.
  useEffect(() => {
    if (estado !== "ok" || !aberto?.snippet || !corpo.current) return;
    const id = requestAnimationFrame(() => {
      if (corpo.current) realcar(corpo.current, aberto.snippet as string);
    });
    return () => cancelAnimationFrame(id);
  }, [estado, conteudo, aberto]);

  if (!aberto) return null;

  const mensagem =
    estado === "carregando" ? te("sourceLoading")
    : estado === "401" ? te("sourceSessionExpired")
    : estado === "403" ? te("sourceForbidden")
    : estado === "404" ? te("sourceMissing")
    : estado === "erro" ? te("sourceError")
    : "";

  return (
    <div className="source-viewer" role="dialog" aria-label={aberto.name}>
      <div className="source-viewer-head">
        <span className="source-viewer-name">{aberto.name}</span>
        <button type="button" className="source-viewer-close" ref={fecharBtn} onClick={fechar}
                aria-label={te("sourceClose")}>
          ×
        </button>
      </div>
      {/* O `mensagem ? <p> : <MarkdownRenderer>` abaixo é o que impede o <mark> inserido por
          `realcar` (fora do React, direto no DOM) de vazar de uma abertura para a próxima: ao
          trocar de ramo, React desmonta a subárvore do MarkdownRenderer e leva os `<mark>`
          junto. Não é por causa do reset de estado/conteúdo acima — é a troca de ramo em si.
          Um futuro "manter o documento anterior visível enquanto carrega o próximo" (trocar
          este ternário por manter o MarkdownRenderer montado com conteúdo antigo) reintroduziria
          o vazamento em silêncio. */}
      <div className="source-viewer-body" ref={corpo}>
        {mensagem ? (
          <p className="muted">{mensagem}</p>
        ) : (
          <>
            {truncado && <p className="muted source-viewer-truncated">{te("sourceTruncated")}</p>}
            <CopilotChatAssistantMessage.MarkdownRenderer content={conteudo} />
          </>
        )}
      </div>
    </div>
  );
}
