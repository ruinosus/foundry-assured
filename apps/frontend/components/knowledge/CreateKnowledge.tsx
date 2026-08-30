"use client";

// Criar base de conhecimento: nomear, e então alimentar por arquivos OU por repositório.
//
// A ordem da interface reflete a ordem do recurso, e não é arbitrária: a base precisa existir
// antes de receber conteúdo, porque o container onde os arquivos vão é derivado do nome dela.
// Um formulário único que fizesse as duas coisas de uma vez esconderia que são duas operações —
// e quando a segunda falhasse, a pessoa não saberia que a primeira funcionou.
//
// O passo 2 tem dois caminhos, e o segundo é a única parte deste produto que não é Microsoft:
// não existe knowledge source de GitHub em primeira parte, então lemos os arquivos e escrevemos
// no blob. Do blob em diante o pipeline oficial retoma.

import { useTranslations } from "next-intl";
import { useState } from "react";
import { AiField } from "@/components/shell/AiField";
import { FieldProposalTool, type FieldProposal } from "@/components/shell/FieldProposal";
import { authedFetch } from "@/lib/auth/api";

type Result = { kind: "ok" | "bad"; text: string } | null;

export function CreateKnowledge({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("knowledgeCreate");
  const tc = useTranslations("common");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);

  const [files, setFiles] = useState<FileList | null>(null);
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const [ref, setRef] = useState("");
  const [subdir, setSubdir] = useState("");

  const call = async (init: RequestInit, path = "") => {
    setBusy(true);
    setResult(null);
    try {
      const target = created ?? name;
      const url = path
        ? `/api/foundry/knowledge/${encodeURIComponent(target)}`
        : "/api/foundry/knowledge";
      const r = await authedFetch(url, init);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setResult({ kind: "bad", text: body?.error ?? `HTTP ${r.status}` });
        return null;
      }
      return body;
    } catch {
      setResult({ kind: "bad", text: tc("backendUnreachable") });
      return null;
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    const body = await call({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    if (!body) return;
    setCreated(body.name);
    setResult({ kind: "ok", text: t("created", { name: body.name }) });
    onCreated();
  };

  const sendFiles = async () => {
    if (!files?.length) return;
    const form = new FormData();
    for (const f of Array.from(files)) form.append("files", f);
    // Sem Content-Type manual: o browser precisa gerar o boundary do multipart.
    const body = await call({ method: "POST", body: form }, "files");
    if (!body) return;
    setResult({ kind: "ok", text: t("uploaded", { count: body.files?.length ?? 0 }) });
    onCreated();
  };

  const importRepo = async () => {
    const body = await call(
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, token, ref, subdir }),
      },
      "github",
    );
    if (!body) return;
    // O token sai do estado assim que a chamada termina: não há razão para ele continuar em
    // memória do browser depois de usado.
    setToken("");
    // O que ficou de fora entra na mensagem. Uma base que importou 40 de 400 arquivos e não diz
    // isso responde com confiança sobre um corpus que ela não tem.
    const parts = [t("imported", { count: body.ingested, repo: body.repo })];
    if (body.skipped_count > 0) parts.push(t("skipped", { count: body.skipped_count }));
    if (body.tree_truncated_by_github) parts.push(t("treeTruncated"));
    setResult({ kind: "ok", text: parts.join(" ") });
    onCreated();
  };

  const aplicar = (p: FieldProposal) => {
    if (p.field === "description") setDescription(p.value);
    else if (p.field === "name") setName(p.value);
    // A base de conhecimento não tem `metadata` no contrato de criação (o backend monta o
    // recurso a partir de nome e descrição), então a procedência ainda não viaja daqui. Dizer
    // isso é melhor que fingir que viaja: ver a nota no commit.
  };

  return (
    <section className="card stack-sm">
      <FieldProposalTool
        onAccept={aplicar}
        resource="knowledge"
        fields={["name", "description"]}
        current={{ name, description }}
      />
      <h3 className="section-title">{t("title")}</h3>

      {result && (
        <div className={`notice ${result.kind === "bad" ? "notice-block" : ""}`}>
          <p className="notice-body">{result.text}</p>
        </div>
      )}

      {/* Passo 1 — a base precisa existir antes de receber conteúdo. */}
      <div className="stack-sm">
        <p className="t-sm strong">{t("step1")}</p>
        <div className="row-tight">
          <input
            className="acct-btn grow"
            placeholder={t("namePlaceholder")}
            value={name}
            disabled={busy || created !== null}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-solid"
            disabled={busy || !name.trim() || created !== null}
            onClick={() => void create()}
          >
            {t("createBtn")}
          </button>
        </div>
        {/* A descrição da base é o que o AGENTE lê para decidir se consulta esta base — não é
            rótulo de vitrine. Escrevê-la bem muda a recuperação, e é por isso que ela ganha as
            ações de IA junto com as demais. */}
        <AiField
          field="description"
          label={t("descriptionPlaceholder")}
          value={description}
          resource={t("resourceKnowledge")}
        >
          <input
            className="acct-btn"
            placeholder={t("descriptionPlaceholder")}
            value={description}
            disabled={busy || created !== null}
            onChange={(e) => setDescription(e.target.value)}
          />
        </AiField>
        <p className="muted t-xs">{t("nameHelp")}</p>
      </div>

      {/* Passo 2 — só depois que a base existe, porque o container vem do nome dela. */}
      <div className="stack-sm">
        <p className="t-sm strong">{t("step2")}</p>
        {!created && <p className="muted t-xs">{t("step2Locked")}</p>}

        <div className="grid g2">
          <div className="stack-sm">
            <p className="t-xs strong">{t("byFiles")}</p>
            <input
              type="file"
              multiple
              className="acct-btn"
              disabled={busy || !created}
              onChange={(e) => setFiles(e.target.files)}
            />
            <p className="muted t-xs">{t("filesHelp")}</p>
            <button
              type="button"
              className="btn"
              disabled={busy || !created || !files?.length}
              onClick={() => void sendFiles()}
            >
              {t("uploadBtn")}
            </button>
          </div>

          <div className="stack-sm">
            <p className="t-xs strong">{t("byRepo")}</p>
            <input
              className="acct-btn"
              placeholder="organizacao/repositorio"
              value={repo}
              disabled={busy || !created}
              onChange={(e) => setRepo(e.target.value)}
            />
            {/* type=password + autoComplete off: token de terceiro não vai para o gerenciador de
                senhas do browser nem fica visível na tela. */}
            <input
              className="acct-btn"
              type="password"
              autoComplete="off"
              placeholder={t("tokenPlaceholder")}
              value={token}
              disabled={busy || !created}
              onChange={(e) => setToken(e.target.value)}
            />
            <div className="row-tight">
              <input
                className="acct-btn grow"
                placeholder={t("refPlaceholder")}
                value={ref}
                disabled={busy || !created}
                onChange={(e) => setRef(e.target.value)}
              />
              <input
                className="acct-btn grow"
                placeholder={t("subdirPlaceholder")}
                value={subdir}
                disabled={busy || !created}
                onChange={(e) => setSubdir(e.target.value)}
              />
            </div>
            <p className="muted t-xs">{t("tokenHelp")}</p>
            <button
              type="button"
              className="btn"
              disabled={busy || !created || !repo.trim() || !token}
              onClick={() => void importRepo()}
            >
              {t("importBtn")}
            </button>
          </div>
        </div>
      </div>

      {created && (
        <p className="muted t-xs">{t("indexingNote")}</p>
      )}
    </section>
  );
}
