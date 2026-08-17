"use client";

// Criar um agente novo.
//
// ISTO FALTAVA, e a falta era do tipo que passa despercebida: publicar versão só existia DENTRO
// do detalhe de um agente, e para chegar ao detalhe o agente já tinha de estar na lista. O
// caminho para o primeiro agente não existia — o backend aceitava (a primeira versão É a
// criação), mas a interface não tinha por onde informar um nome novo.
//
// Não há endpoint separado de "criar": publicar a primeira versão cria o agente. O formulário
// diz isso em vez de esconder — e por isso o botão é "Criar e publicar versão", não "Criar".

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authedFetch } from "@/lib/auth/api";

export function CreateAgent({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("agentCreate");
  const td = useTranslations("agentDetail");
  const tc = useTranslations("common");
  const router = useRouter();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [doc, setDoc] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(doc);
    } catch {
      setError(td("invalidJson"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await authedFetch(`/api/foundry/agents/${encodeURIComponent(name)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ definition: parsed, description }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      onCreated();
      // Vai direto para o detalhe: é lá que estão versões, sessões e as próximas ações. Deixar
      // a pessoa na lista a obrigaria a procurar o que acabou de criar.
      router.push(`/agents/${encodeURIComponent(body.name ?? name)}`);
    } catch {
      setError(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="btn btn-solid" onClick={() => setOpen(true)}>
        {t("newBtn")}
      </button>
    );
  }

  return (
    <section className="card stack-sm">
      <h3 className="section-title">{t("title")}</h3>
      <p className="muted t-sm">{t("help")}</p>

      {error && (
        <div className="notice notice-block">
          <p className="notice-body">{error}</p>
        </div>
      )}

      <input
        className="acct-btn"
        placeholder={t("namePlaceholder")}
        value={name}
        disabled={busy}
        onChange={(e) => setName(e.target.value)}
      />
      <p className="muted t-xs">{t("nameHelp")}</p>

      <input
        className="acct-btn"
        placeholder={t("descriptionPlaceholder")}
        value={description}
        disabled={busy}
        onChange={(e) => setDescription(e.target.value)}
      />

      <textarea
        className="acct-btn"
        rows={10}
        spellCheck={false}
        placeholder={td("examplePlaceholder")}
        value={doc}
        disabled={busy}
        onChange={(e) => setDoc(e.target.value)}
      />

      <div className="row">
        <button
          type="button"
          className="btn btn-solid"
          disabled={busy || !name.trim() || !doc.trim()}
          onClick={() => void create()}
        >
          {t("createBtn")}
        </button>
        <button type="button" className="btn" disabled={busy} onClick={() => setOpen(false)}>
          {tc("cancel")}
        </button>
      </div>
    </section>
  );
}
