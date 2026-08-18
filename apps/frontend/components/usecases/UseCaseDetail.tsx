"use client";

// Detalhe do caso de uso — ler o fluxo, montá-lo, e ver o que ele produziu.
//
// Três coisas numa tela, porque são as três perguntas que a mesma pessoa faz em sequência: o que
// este assistente faz, como mudo, e está funcionando.
//
// O CANVAS É UMA SEQUÊNCIA, não uma tela livre. A linguagem declarativa não tem "nós e arestas" —
// é lista aninhada de ações. Um editor que deixasse ligar qualquer coisa a qualquer coisa
// produziria YAML que não monta, e o erro só apareceria ao publicar. A restrição é a
// funcionalidade: aqui só se desenha o que roda.

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { useMyRoles, canAdmin } from "@/lib/auth/roles";
import { type Flow, type FlowStep, fromYaml, toYaml, validate } from "@/lib/flowCanvas";
import { Outcomes } from "@/components/usecases/Outcomes";

type UseCase = {
  id: string;
  name: string;
  description: string;
  agents: { name: string; state: string | null; version: string | null; runtime: string | null }[];
  steps: { id: string | null; label: string | null; kind: string; waits_for_human: boolean }[];
  runtime: string;
  flow: string | null;
};

/** Os tipos de passo que o canvas oferece. O RÓTULO vem do dicionário na hora de criar — aqui
 *  só a forma, porque `kind` e `variable` são contrato da linguagem, não texto. */
const NOVO: Record<string, Omit<FlowStep, "label">> = {
  agent: { kind: "agent", id: "novo_passo", agent: "" },
  message: { kind: "message", id: "mensagem", text: "" },
  approval: { kind: "approval", id: "aprovacao", prompt: "", variable: "aprovacao" },
  question: { kind: "question", id: "pergunta", text: "", variable: "resposta" },
} as Record<string, Omit<FlowStep, "label">>;

export function UseCaseDetail({ id }: { id: string }) {
  const t = useTranslations("useCaseDetail");
  const tu = useTranslations("useCases");
  const tc = useTranslations("common");
  const roles = useMyRoles();
  const admin = canAdmin(roles);

  const [caso, setCaso] = useState<UseCase | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [movido, setMovido] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [flow, setFlow] = useState<Flow>({ steps: [] });
  const [editavel, setEditavel] = useState(true);
  const [editando, setEditando] = useState(false);

  const load = useCallback(async () => {
    setErro(null);
    try {
      const r = await authedFetch(`/api/usecases/${encodeURIComponent(id)}`, { cache: "no-store" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        // O backend distingue "não existe" de "mudou de lugar". Um link antigo para um
        // assistente de TELA não deve dizer que o agente sumiu — ele existe, e a medição dele
        // fica noutra tela.
        const codigo = (body?.error as { code?: string } | undefined)?.code;
        if (codigo === "moved_to_assistants") {
          setMovido(true);
          return;
        }
        setErro(typeof body?.error === "string" ? body.error : `HTTP ${r.status}`);
        return;
      }
      setCaso(body);
      if (body.flow) {
        const { flow: f, editable } = fromYaml(body.flow);
        setFlow(f);
        setEditavel(editable);
      } else {
        setFlow({ steps: [] });
        setEditavel(true);
      }
    } catch {
      setErro(tc("backendUnreachable"));
    }
  }, [id, tc]);

  useEffect(() => {
    void load();
  }, [load]);

  const publicar = async () => {
    const problemas = validate(flow);
    if (problemas.length) {
      setAviso(t("invalidFlow", { count: problemas.length }));
      return;
    }
    setBusy(true);
    setAviso(null);
    try {
      const yaml = toYaml(flow, { name: caso?.name ?? id });
      const r = await authedFetch(`/api/usecases/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        // O backend valida pelo próprio WorkflowFactory — a mensagem dele diz o que o runtime
        // recusou, e é mais precisa que qualquer coisa que eu escrevesse aqui.
        setAviso(body?.error ?? `HTTP ${r.status}`);
        return;
      }
      setAviso(t("saved"));
      setEditando(false);
      void load();
    } catch {
      setAviso(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  const mover = (i: number, delta: number) => {
    const novo = [...flow.steps];
    const alvo = i + delta;
    if (alvo < 0 || alvo >= novo.length) return;
    [novo[i], novo[alvo]] = [novo[alvo], novo[i]];
    setFlow({ steps: novo });
  };

  const atualizar = (i: number, campo: string, valor: string) => {
    const novo = [...flow.steps];
    novo[i] = { ...novo[i], [campo]: valor } as FlowStep;
    setFlow({ steps: novo });
  };

  if (movido) {
    return (
      <div className="notice notice-block">
        <p className="notice-body">{t("movedToAssistants")}</p>
        <Link className="btn btn-solid" href="/assistants">
          {t("goToAssistants")}
        </Link>
      </div>
    );
  }

  if (erro) {
    return (
      <div className="notice notice-block">
        <p className="notice-body">{erro}</p>
        <button type="button" className="btn" onClick={() => void load()}>
          {tc("retry")}
        </button>
      </div>
    );
  }

  if (!caso) return <div className="skeleton-list" aria-hidden><div className="skeleton-row" /></div>;

  return (
    <section className="stack">
      <header className="between">
        <div>
          <p className="t-xs muted-line">
            <Link href="/usecases">{tu("title")}</Link>
          </p>
          <h2 className="page-title">{caso.name}</h2>
          {caso.description && <p className="page-sub">{caso.description}</p>}
        </div>
        {admin && caso.runtime === "declarative" && (
          <button
            type="button"
            className="btn"
            disabled={!editavel}
            title={editavel ? undefined : t("readOnlyHint")}
            onClick={() => setEditando((v) => !v)}
          >
            {editando ? tc("cancel") : t("editFlow")}
          </button>
        )}
      </header>

      {aviso && (
        <div className="notice">
          <p className="notice-body">{aviso}</p>
        </div>
      )}

      {/* Um fluxo com construções que o canvas não representa abre em LEITURA. Salvar por cima
          apagaria condições e loops que alguém escreveu — perder trabalho em silêncio é pior que
          recusar a edição. */}
      {!editavel && (
        <div className="notice notice-wait">
          <p className="notice-body">{t("readOnly")}</p>
        </div>
      )}

      {!editando && (
        <div className="stack-sm">
          <h3 className="section-title">{t("flowTitle")}</h3>
          {flow.steps.length === 0 ? (
            <p className="muted t-sm">{t("noFlow")}</p>
          ) : (
            <ol className="flow-read">
              {flow.steps.map((s, i) => (
                <li key={s.id + String(i)} className={s.kind === "approval" ? "waits" : ""}>
                  <span className="flow-kind">{t(`kind_${s.kind}`)}</span>
                  <span className="flow-label">{s.label}</span>
                  {s.kind === "agent" && s.agent && (
                    <span className="t-xs t-mono muted-line">{s.agent}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {editando && (
        <div className="stack-sm">
          <h3 className="section-title">{t("canvasTitle")}</h3>
          <p className="muted t-sm">{t("canvasHelp")}</p>

          <ol className="flow-edit">
            {flow.steps.map((s, i) => (
              <li key={i} className="flow-node">
                <div className="between">
                  <span className="flow-kind">{t(`kind_${s.kind}`)}</span>
                  <div className="row-tight">
                    <button type="button" className="acct-btn" onClick={() => mover(i, -1)} disabled={i === 0}>↑</button>
                    <button type="button" className="acct-btn" onClick={() => mover(i, 1)} disabled={i === flow.steps.length - 1}>↓</button>
                    <button
                      type="button"
                      className="acct-btn"
                      onClick={() => setFlow({ steps: flow.steps.filter((_, j) => j !== i) })}
                    >
                      ✕
                    </button>
                  </div>
                </div>

                <input
                  className="acct-btn"
                  value={s.label}
                  placeholder={t("stepLabel")}
                  onChange={(e) => atualizar(i, "label", e.target.value)}
                />

                {s.kind === "agent" && (
                  <select
                    className="acct-btn"
                    value={s.agent}
                    onChange={(e) => atualizar(i, "agent", e.target.value)}
                  >
                    <option value="">{t("pickAgent")}</option>
                    {caso.agents.map((a) => (
                      <option key={a.name} value={a.name}>{a.name}</option>
                    ))}
                  </select>
                )}

                {(s.kind === "message" || s.kind === "question") && (
                  <textarea
                    className="acct-btn"
                    rows={2}
                    value={s.text}
                    placeholder={t("stepText")}
                    onChange={(e) => atualizar(i, "text", e.target.value)}
                  />
                )}

                {s.kind === "approval" && (
                  <textarea
                    className="acct-btn"
                    rows={2}
                    value={s.prompt}
                    placeholder={t("approvalPrompt")}
                    onChange={(e) => atualizar(i, "prompt", e.target.value)}
                  />
                )}
              </li>
            ))}
          </ol>

          <div className="row-tight">
            {Object.keys(NOVO).map((k) => (
              <button
                key={k}
                type="button"
                className="acct-btn"
                onClick={() =>
                  setFlow({
                    steps: [
                      ...flow.steps,
                      {
                        ...NOVO[k],
                        id: `${k}_${flow.steps.length + 1}`,
                        label: t(`kind_${k}`),
                      } as FlowStep,
                    ],
                  })
                }
              >
                + {t(`kind_${k}`)}
              </button>
            ))}
          </div>

          {/* O YAML fica VISÍVEL. Quem monta pelo canvas não precisa lê-lo, mas quem for manter
              precisa saber que ele existe e é um formato aberto — não um blob nosso. */}
          <details className="stack-sm">
            <summary className="t-sm">{t("showYaml")}</summary>
            <pre className="doc-preview">{toYaml(flow, { name: caso.name })}</pre>
          </details>

          <div className="row">
            <button type="button" className="btn btn-solid" disabled={busy} onClick={() => void publicar()}>
              {busy ? t("saving") : t("saveFlow")}
            </button>
          </div>
        </div>
      )}

      {/* Resultados ANTES das peças: quem é de negócio quer saber se funciona, e só depois de
          que é feito. A ordem da tela responde as perguntas na ordem em que aparecem. */}
      <Outcomes caseId={id} />

      <div className="stack-sm">
        <h3 className="section-title">{t("piecesTitle")}</h3>
        <p className="muted t-sm">{t("piecesHelp")}</p>
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t("colAgent")}</th>
                <th>{t("colVersion")}</th>
                <th>{t("colRuntime")}</th>
              </tr>
            </thead>
            <tbody>
              {caso.agents.map((a) => (
                <tr key={a.name}>
                  <td>
                    <Link className="strong" href={`/agents/${encodeURIComponent(a.name)}`}>
                      {a.name}
                    </Link>
                  </td>
                  <td className="t-mono t-sm">{a.version ?? "—"}</td>
                  <td className="t-sm">{a.runtime ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
