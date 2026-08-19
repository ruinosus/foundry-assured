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
import { useEffect, useRef, useState } from "react";

interface Aberto {
  domainId: string;
  name: string;
  snippet?: string;
}

/** Envolve o trecho em <mark> DEPOIS da renderização, andando pelos nós de texto.
 *
 * Marcar o markdown ANTES de renderizar quebraria bloco de código, tabela e link — e é em
 * documento técnico que o trecho cai nesses lugares. Aqui não há sintaxe para quebrar.
 *
 * A comparação é feita em texto NORMALIZADO (espaço colapsado) porque o trecho vem do ÍNDICE
 * e o documento vem do BLOB: eles divergem em quebra de linha e indentação. O mapa `posicoes`
 * é o que traduz um índice do texto normalizado de volta para (nó, deslocamento) reais.
 */
function realcar(raiz: HTMLElement, trecho: string): boolean {
  const alvo = trecho.replace(/\s+/g, " ").trim();
  if (alvo.length < 24) return false;

  const nos: Text[] = [];
  const caminhador = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
  for (let n = caminhador.nextNode(); n; n = caminhador.nextNode()) nos.push(n as Text);

  // Texto normalizado + posição de cada caractere no nó de origem.
  let plano = "";
  const posicoes: Array<{ no: Text; off: number }> = [];
  let espacoPendente = false;
  for (const no of nos) {
    const bruto = no.data;
    for (let i = 0; i < bruto.length; i++) {
      if (/\s/.test(bruto[i])) {
        espacoPendente = plano.length > 0;
        continue;
      }
      if (espacoPendente) {
        plano += " ";
        posicoes.push({ no, off: i });
        espacoPendente = false;
      }
      plano += bruto[i];
      posicoes.push({ no, off: i });
    }
  }

  // O maior prefixo do trecho que exista no documento — divergências de normalização entre
  // índice e blob costumam ficar no FIM do trecho, então encurtar pelo fim é o que resolve.
  let inicio = -1;
  let usados = 0;
  for (let corte = alvo.length; corte >= 24; corte -= Math.max(8, Math.floor(corte / 8))) {
    inicio = plano.indexOf(alvo.slice(0, corte));
    if (inicio >= 0) {
      usados = corte;
      break;
    }
  }
  if (inicio < 0) return false;

  // Marca por NÓ: um Range que cruza fronteira de elemento não aceita surroundContents.
  const fim = inicio + usados - 1;
  const porNo = new Map<Text, { de: number; ate: number }>();
  for (let i = inicio; i <= fim && i < posicoes.length; i++) {
    const { no, off } = posicoes[i];
    const faixa = porNo.get(no);
    if (!faixa) porNo.set(no, { de: off, ate: off });
    else faixa.ate = off;
  }

  let primeira: HTMLElement | null = null;
  for (const [no, faixa] of porNo) {
    const range = document.createRange();
    range.setStart(no, faixa.de);
    range.setEnd(no, Math.min(faixa.ate + 1, no.data.length));
    const marca = document.createElement("mark");
    marca.className = "source-hit";
    try {
      range.surroundContents(marca);
    } catch {
      continue; // nó já alterado por uma marca anterior — segue para o próximo
    }
    if (!primeira) primeira = marca;
  }

  const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  primeira?.scrollIntoView({ block: "center", behavior: reduzMovimento ? "auto" : "smooth" });
  return primeira !== null;
}

export function SourceViewer() {
  const te = useTranslations("evidence");
  const [aberto, setAberto] = useState<Aberto | null>(null);
  const [estado, setEstado] = useState<"carregando" | "ok" | "403" | "404" | "erro">("carregando");
  const [conteudo, setConteudo] = useState("");
  const corpo = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ao = (e: Event) => setAberto((e as CustomEvent).detail as Aberto);
    window.addEventListener("abrir-fonte", ao);
    return () => window.removeEventListener("abrir-fonte", ao);
  }, []);

  useEffect(() => {
    if (!aberto) return;
    let cancelado = false;
    setEstado("carregando");
    setConteudo("");
    fetch(`/api/source/${encodeURIComponent(aberto.domainId)}/${encodeURIComponent(aberto.name)}`)
      .then(async (r) => {
        if (cancelado) return;
        if (r.status === 403) return setEstado("403");
        if (r.status === 404) return setEstado("404");
        if (!r.ok) return setEstado("erro");
        const body = await r.json();
        setConteudo(String(body?.content ?? ""));
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
    : estado === "403" ? te("sourceForbidden")
    : estado === "404" ? te("sourceMissing")
    : estado === "erro" ? te("sourceError")
    : "";

  return (
    <div className="source-viewer" role="dialog" aria-label={aberto.name}>
      <div className="source-viewer-head">
        <span className="source-viewer-name">{aberto.name}</span>
        <button type="button" className="source-viewer-close" onClick={() => setAberto(null)}
                aria-label={te("sourceClose")}>
          ×
        </button>
      </div>
      <div className="source-viewer-body" ref={corpo}>
        {mensagem ? (
          <p className="muted">{mensagem}</p>
        ) : (
          <CopilotChatAssistantMessage.MarkdownRenderer content={conteudo} />
        )}
      </div>
    </div>
  );
}
