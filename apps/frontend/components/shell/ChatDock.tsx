"use client";

// Chat lateral nas telas de gestão — o padrão do `aap-kb`, com uma diferença de escopo.
//
// POR QUE UM CHAT AQUI. As telas de agentes, conhecimento e skills mostram catálogo e formulário;
// nenhuma delas responde "qual base eu uso para isso?" ou "como escrevo essa instrução?". O chat
// ao lado é onde essas perguntas cabem, sem tirar a pessoa do que ela estava fazendo.
//
// QUAL AGENTE ATENDE. Reusa os domínios que já existem, em vez de inventar um: o `selfwiki`
// conhece este repositório e responde sobre como as peças se encaixam. Criar um agente novo só
// para isto seria mais um recurso a manter, e a pergunta "o que este produto faz" já tem dono.
//
// A escolha fica com a pessoa: o seletor lista os domínios do registry. Fixar um deles decidiria
// por ela num contexto em que a pergunta varia — quem está montando um agente de plataforma quer
// o `platform`, não o `selfwiki`.

import { CopilotChat } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { useMemo, useRef } from "react";
import { useChatDock } from "@/lib/chat-dock";
import { DOMAINS } from "@/lib/domains";

export function ChatDock() {
  const t = useTranslations("chatDock");
  const td = useTranslations("domains");
  const { open, hide, agentId, setAgentId } = useChatDock();

  // Uma thread POR AGENTE. Antes o provider era remontado (`key={agentId}`) para não vazar o
  // histórico de um para o outro; remontar agora apagaria o rascunho do wizard junto, porque o
  // provider passou a envolver a página inteira. Separar por identidade faz o mesmo trabalho sem
  // destruir nada — e o histórico volta ao trocar de volta, em vez de recomeçar.
  const threads = useRef<Record<string, string>>({});
  const threadId = useMemo(() => {
    threads.current[agentId] ??= crypto.randomUUID();
    return threads.current[agentId];
  }, [agentId]);

  if (!open) return null;

  return (
    <aside className="chat-dock" aria-label={t("title")}>
      <header className="chat-dock-head">
        <select
          className="acct-btn"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          aria-label={t("agentLabel")}
        >
          {DOMAINS.map((d) => (
            <option key={d.id} value={d.id}>
              {td(`${d.id}.label`)}
            </option>
          ))}
        </select>
        <button type="button" className="acct-btn" onClick={hide} aria-label={t("close")}>
          ✕
        </button>
      </header>

      {/* Sem provider próprio: quem provê é o shell (DockProvider), para que uma tool registrada
          por uma TELA seja visível ao agente daqui. */}
      <div className="chat-dock-body copilotkit-chat-host">
        <CopilotChat agentId={agentId} threadId={threadId} />
      </div>
    </aside>
  );
}
