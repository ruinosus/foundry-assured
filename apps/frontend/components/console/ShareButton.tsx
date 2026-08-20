"use client";

// Compartilhar a conversa ATIVA — liga/desliga e copia o link (`/d/<domínio>?c=<threadId>`).
//
// POR QUE SÓ A CONVERSA ATIVA, e não um botão por item da lista. A lista (ConversationsPanel) já
// lê metadata de toda conversa do usuário numa chamada só (`list_blobs`); mostrar o estado de
// compartilhamento de CADA item exigiria uma consulta a mais por item ao índice de
// compartilhamento (`conversations-shared`, um blob por conversa — ver backend). Para a conversa
// que está na tela, uma consulta é suficiente e o custo não escala com o tamanho da lista.
//
// As citações NÃO viajam por aqui: o link leva ao texto e ao NOME das fontes; o documento em si
// continua atrás de `/source`, que reautoriza com a identidade de quem clica — este componente
// não sabe nada sobre isso, só ativa/desativa a leitura da TRANSCRIÇÃO.

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { sharedConversationUrl } from "@/lib/conversation-url";

export function ShareButton({ agent, conversationId }: { agent: string; conversationId: string }) {
  const t = useTranslations("console");
  const [shared, setShared] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  // O estado nasce do backend, não de suposição: abrir a conversa não significa que ela já
  // estava compartilhada, e uma conversa nova (sem turno gravado ainda) responde 404 — que aqui
  // só quer dizer "não compartilhada", não um erro para mostrar.
  useEffect(() => {
    let ativo = true;
    setAviso(null);
    if (!conversationId) return;
    authedFetch(`/api/conversations/${encodeURIComponent(agent)}/${encodeURIComponent(conversationId)}/share`, {
      cache: "no-store",
    })
      .then((r) => r.json().catch(() => ({})))
      .then((body) => {
        if (ativo) setShared(Boolean(body?.shared));
      })
      .catch(() => {
        if (ativo) setShared(false);
      });
    return () => {
      ativo = false;
    };
  }, [agent, conversationId]);

  const alternar = async () => {
    setOcupado(true);
    setAviso(null);
    try {
      const r = await authedFetch(
        `/api/conversations/${encodeURIComponent(agent)}/${encodeURIComponent(conversationId)}/share`,
        { method: shared ? "DELETE" : "POST" },
      );
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        // 404 ao LIGAR é quase sempre "ainda não há turno gravado nesta conversa" — a posse é
        // confirmada lendo a própria conversa (ver listing.share_conversation), e conversa vazia
        // não tem o que compartilhar ainda.
        setAviso(shared ? t("share.errorOff") : t("share.errorOn"));
        return;
      }
      setShared(Boolean(body?.shared));
      if (body?.shared) {
        // A cópia é o PONTO do botão — sem ela, "compartilhar" ligaria o link mas ninguém saberia
        // qual link é. `writeText` falha em contexto não seguro (http local antigo); degrada
        // para o aviso, não para uma exceção não tratada.
        try {
          await navigator.clipboard.writeText(sharedConversationUrl(agent, conversationId));
          setAviso(t("share.copied"));
        } catch {
          setAviso(t("share.on"));
        }
      }
    } finally {
      setOcupado(false);
    }
  };

  if (!conversationId) return null;

  return (
    <div className="share-btn-wrap">
      <button
        type="button"
        className={`share-btn${shared ? " on" : ""}`}
        onClick={() => void alternar()}
        disabled={ocupado}
        title={shared ? t("share.off") : t("share.button")}
      >
        {shared ? t("share.shared") : t("share.button")}
      </button>
      {aviso && <span className="t-xs muted-line">{aviso}</span>}
    </div>
  );
}
