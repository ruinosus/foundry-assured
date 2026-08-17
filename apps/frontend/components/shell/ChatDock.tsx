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

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { useChatDock } from "@/lib/chat-dock";
import { DOMAINS } from "@/lib/domains";

export function ChatDock({ authorization }: { authorization?: string }) {
  const t = useTranslations("chatDock");
  const td = useTranslations("domains");
  const locale = useLocale();
  const { open, hide } = useChatDock();
  // `selfwiki` como ponto de partida: é o domínio que sabe explicar o próprio produto.
  const [agentId, setAgentId] = useState(
    DOMAINS.find((d) => d.id === "selfwiki")?.id ?? DOMAINS[0].id,
  );

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

      {/* Provider próprio, com a mesma configuração do console: o dock vive fora da rota de
          domínio, então não herda o provider de lá. `key` força remontagem ao trocar de agente —
          sem isso o histórico de um vazaria para o outro. */}
      <div className="chat-dock-body copilotkit-chat-host">
        <CopilotKitProvider
          key={agentId}
          runtimeUrl="/api/copilotkit"
          headers={{
            ...(authorization ? { Authorization: authorization } : {}),
            "Accept-Language": locale,
          }}
        >
          <CopilotChat agentId={agentId} />
        </CopilotKitProvider>
      </div>
    </aside>
  );
}
