"use client";

// As conversas anteriores deste domínio, e o botão de voltar para uma.
//
// POR QUE NÃO É O `<CopilotThreadsDrawer>` DO COPILOTKIT. O pacote traz um drawer de threads
// pronto (`useThreads`, `CopilotThreadsDrawer`) e ele seria a escolha óbvia — mas a docstring dele
// diz "threads managed by the Intelligence platform", e o bundle bate em `cloud.copilotkit` com
// `publicApiKey`. É o SaaS da CopilotKit, não o nosso runtime: usá-lo mandaria a conversa do
// usuário para um terceiro. As nossas ficam no Storage do próprio tenant, sob Entra.
//
// O que o pacote oferece e NÓS usamos é o `threadId` controlado por prop no `<CopilotChat>` —
// isso é API local, sem nuvem no meio.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

export type Conversation = {
  id: string;
  agent: string;
  title: string;
  updated_at: string;
  messages: number;
  source: "backend" | "foundry";
  resumable: boolean;
};

export function ConversationsPanel({
  agent,
  activeId,
  onOpen,
  onNew,
}: {
  agent: string;
  activeId: string;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  const t = useTranslations("conversations");
  const [itens, setItens] = useState<Conversation[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const r = await authedFetch(`/api/conversations?agent=${encodeURIComponent(agent)}`, {
        cache: "no-store",
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      setItens(body.conversations ?? []);
    } catch {
      setErro(t("unreachable"));
    } finally {
      setCarregando(false);
    }
  }, [agent, t]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Recarrega quando a conversa ativa muda: o turno que acabou de ser gravado precisa aparecer
  // na lista, e uma conversa nova só existe depois da primeira resposta.
  useEffect(() => {
    if (!activeId) return;
    const id = setTimeout(() => void carregar(), 2500);
    return () => clearTimeout(id);
  }, [activeId, carregar]);

  return (
    <aside className="conv-panel">
      <div className="between">
        <h3 className="section-title">{t("title")}</h3>
        <button type="button" className="acct-btn" onClick={onNew} title={t("new")}>
          + {t("new")}
        </button>
      </div>

      {erro && <p className="t-xs bad-line">{erro}</p>}

      {!erro && carregando && itens.length === 0 && (
        <div className="skeleton-list" aria-hidden>
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      )}

      {!erro && !carregando && itens.length === 0 && <p className="muted t-xs">{t("empty")}</p>}

      <ul className="conv-list">
        {itens.map((c) => (
          <li key={`${c.source}-${c.id}`}>
            <button
              type="button"
              className={`conv-item${c.id === activeId ? " on" : ""}`}
              onClick={() => onOpen(c.id)}
            >
              {/* Título vazio acontece nas sessões do Foundry: o serviço guarda id e timestamps,
                  nunca o texto. Mostrar um rótulo genérico é honesto; inventar um assunto não. */}
              <span className="conv-title">{c.title || t("untitled")}</span>
              <span className="conv-meta">
                {c.updated_at ? new Date(c.updated_at).toLocaleString() : "—"}
                {c.source === "foundry" && <span className="pill t-xs">{t("inFoundry")}</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
