"use client";

// Starter prompts — the antidote to the "blank box / prompt paralysis" anti-pattern.
// Per-domain chips (from lib/domains.ts) that send on click via the AG-UI agent
// (addMessage + runAgent). Shown only until the conversation starts, then they get out
// of the way.

import { useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import type { Domain } from "@/lib/domains";

export function SuggestedPrompts({ domain }: { domain: Domain }) {
  const t = useTranslations("console");
  const td = useTranslations("domains");
  const { agent } = useAgent({ agentId: domain.id });
  const { copilotkit } = useCopilotKit();
  const [hasMessages, setHasMessages] = useState(false);

  useEffect(() => {
    if (!agent) return;
    const sync = () => setHasMessages((agent.messages?.length ?? 0) > 0);
    sync();
    const sub = agent.subscribe({
      onRunInitialized: () => setHasMessages(true),
      onMessagesChanged: sync,
    });
    return () => sub.unsubscribe();
  }, [agent]);

  if (hasMessages) return null;

  const send = (text: string) => {
    if (!agent) return;
    // `crypto.randomUUID()` direto, como em `send-to-dock.ts`, que é o mesmo caminho. O
    // fallback com `Math.random()` protegia de um navegador que este app não suporta, e em
    // troca fazia o corpo do componente chamar função impura.
    const id = crypto.randomUUID();
    agent.addMessage({ id, role: "user", content: text });
    setHasMessages(true);
    // Pelo CORE, não pelo agente: é o core que monta a lista de tools do frontend. Aqui não havia
    // sintoma porque nenhum domínio de chip declara tool — mas o chip e o campo do wizard usam o
    // mesmo caminho, e deixar um certo e o outro errado garante que o próximo a copiar copie o
    // errado.
    void copilotkit.runAgent({ agent });
  };

  return (
    <div className="suggest">
      <span className="suggest-label">{t("suggested")}</span>
      <div className="suggest-chips">
        {/* `raw` porque a chave é uma LISTA, não uma frase: `t()` devolveria texto formatado e
            perderia os itens. Os prompts precisam viver no dicionário como os demais — em
            inglês, "abre um chamado pra mim?" não convida ninguém a clicar. */}
        {(td.raw(`${domain.id}.suggested`) as string[]).map((q) => (
          <button key={q} className="suggest-chip" onClick={() => send(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
