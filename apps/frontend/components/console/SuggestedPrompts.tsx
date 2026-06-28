"use client";

// Starter prompts — the antidote to the "blank box / prompt paralysis" anti-pattern.
// Per-domain chips (from lib/domains.ts) that send on click via the AG-UI agent
// (addMessage + runAgent). Shown only until the conversation starts, then they get out
// of the way.

import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";
import type { Domain } from "@/lib/domains";

export function SuggestedPrompts({ domain }: { domain: Domain }) {
  const { agent } = useAgent({ agentId: domain.id });
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
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.round(Math.random() * 1e6)}`;
    agent.addMessage({ id, role: "user", content: text });
    setHasMessages(true);
    void agent.runAgent();
  };

  return (
    <div className="suggest">
      <span className="suggest-label">Experimente:</span>
      <div className="suggest-chips">
        {domain.suggested.map((q) => (
          <button key={q} className="suggest-chip" onClick={() => send(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
