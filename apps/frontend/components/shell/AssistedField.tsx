"use client";

// Campo assistido — o padrão `AIFieldBlock` do um projeto anterior, adaptado.
//
// A DIFERENÇA EM RELAÇÃO AO ORIGINAL, e por que ela é aceitável. No um projeto anterior o clique manda um
// prompt ao CHAT, e quem escreve o campo é o agente pelo caminho normal — o que evita criar um
// segundo caminho de escrita. Aqui não há chat ao lado do wizard, então a sugestão volta como
// PROPOSTA: aparece abaixo do campo, e só entra se a pessoa clicar em usar.
//
// Não é o mesmo desenho, mas preserva a propriedade que importa: **o texto só entra no campo por
// decisão humana**. Um botão que preenchesse direto seria a via paralela que o padrão original
// existe para impedir.
//
// As ações mudam com o estado, porque a pergunta muda: campo vazio pede "escrever", campo cheio
// pede "melhorar". Oferecer as duas sempre faria metade dos botões não fazer sentido.

import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import { authedFetch } from "@/lib/auth/api";

export function AssistedField({
  field,
  label,
  value,
  context,
  onAccept,
  children,
}: {
  /** Nome técnico do campo — vai no pedido, não na tela. */
  field: string;
  /** Rótulo humano, mostrado acima do campo. */
  label: string;
  value: string;
  /** O que o modelo precisa saber: nome do recurso, bases disponíveis, toolboxes. */
  context: Record<string, unknown>;
  onAccept: (texto: string) => void;
  children: ReactNode;
}) {
  const t = useTranslations("assist");
  const tc = useTranslations("common");
  const [busy, setBusy] = useState(false);
  const [sugestao, setSugestao] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [instrucao, setInstrucao] = useState<string | null>(null);

  const pedir = async (action: "gerar" | "revisar", extra?: string) => {
    setBusy(true);
    setErro(null);
    setSugestao(null);
    try {
      const r = await authedFetch("/api/foundry/assist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          field,
          value,
          context: { ...context, ...(extra ? { instrucao: extra } : {}) },
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      const texto = String(body?.suggestion ?? "").trim();
      if (!texto) {
        setErro(t("empty"));
        return;
      }
      setSugestao(texto);
      setInstrucao(null);
    } catch {
      setErro(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  const temValor = value.trim().length > 0;

  return (
    <div className="assisted">
      <div className="between">
        <label className="assisted-label">{label}</label>
        <div className="assisted-actions">
          <button
            type="button"
            className="acct-btn"
            disabled={busy}
            onClick={() => void pedir(temValor ? "revisar" : "gerar")}
          >
            {busy ? t("working") : temValor ? t("review") : t("generate")}
          </button>
          <button
            type="button"
            className="acct-btn"
            disabled={busy}
            title={t("custom")}
            onClick={() => setInstrucao((i) => (i === null ? "" : null))}
          >
            {t("customIcon")}
          </button>
        </div>
      </div>

      {children}

      {instrucao !== null && (
        <div className="row-tight">
          <input
            className="acct-btn grow"
            placeholder={t("customPlaceholder")}
            value={instrucao}
            disabled={busy}
            onChange={(e) => setInstrucao(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && instrucao.trim()) void pedir("gerar", instrucao.trim());
            }}
          />
          <button
            type="button"
            className="btn"
            disabled={busy || !instrucao.trim()}
            onClick={() => void pedir("gerar", instrucao.trim())}
          >
            {t("send")}
          </button>
        </div>
      )}

      {erro && <p className="t-xs bad-line">{erro}</p>}

      {/* A proposta é mostrada inteira antes de qualquer coisa entrar no campo. Substituir o
          conteúdo direto tiraria da pessoa a chance de comparar com o que ela escreveu. */}
      {sugestao && (
        <div className="assisted-suggestion">
          <p className="t-xs muted-line">{t("suggestionTitle")}</p>
          <p className="assisted-text">{sugestao}</p>
          <div className="row-tight">
            <button
              type="button"
              className="btn btn-solid"
              onClick={() => {
                onAccept(sugestao);
                setSugestao(null);
              }}
            >
              {t("use")}
            </button>
            <button type="button" className="btn" onClick={() => setSugestao(null)}>
              {t("discard")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
