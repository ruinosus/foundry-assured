"use client";

// Wizard de skill — quatro passos, no molde do um projeto anterior.
//
// O que ele substitui: um campo de texto pedindo JSON cru. Quem sabe escrever aquele JSON não
// precisa deste produto; quem precisa dele não sabe escrevê-lo. A sequência ensina enquanto
// preenche, e o documento sai pronto no fim.
//
// O PASSO 3 É O PONTO. Skill de verdade não é uma string de instruções: tem scripts que ela
// executa e referências que ela consulta. `create_from_files` do Foundry aceita isso (zip ou
// vários arquivos), e o agrupamento por função — em vez de uma pilha plana — é o que torna a
// skill legível para quem for mantê-la depois.
//
// Duas validações vivem aqui E no backend, de propósito: nome de recurso e nome de arquivo. O
// backend é a fronteira real (a interface não é fronteira de segurança); a tela existe para que
// erro de digitação tenha resposta imediata, em vez de uma viagem até o Azure.

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { AiField } from "@/components/shell/AiField";
import { FieldProposalTool, type FieldProposal } from "@/components/shell/FieldProposal";

/** Os arquivos são agrupados por função — o serviço preserva o caminho, então o grupo vira pasta. */
const GRUPOS = ["scripts", "references"] as const;
type Grupo = (typeof GRUPOS)[number];

type Arquivo = { grupo: Grupo; nome: string; conteudo: string };

// Mesmas regras do backend (`names.py` e `_safe_blob_name`), aplicadas antes da viagem.
const NOME_RECURSO = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const NOME_ARQUIVO = /^[a-zA-Z0-9._-]+$/;

/** Recusa travessia de diretório: o serviço trata `/` como hierarquia. */
function nomeArquivoValido(nome: string): boolean {
  if (!nome || nome.includes("/") || nome.includes("..") || nome === "." || nome.startsWith("."))
    return false;
  return NOME_ARQUIVO.test(nome);
}

export function SkillWizard({
  existentes,
  onConcluido,
  onCancelar,
}: {
  /** Nomes já usados — a checagem de duplicidade acontece ANTES de sair do passo 1. */
  existentes: string[];
  onConcluido: () => void;
  onCancelar: () => void;
}) {
  const t = useTranslations("skillWizard");
  const tc = useTranslations("common");

  const [passo, setPasso] = useState<1 | 2 | 3 | 4>(1);
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [instrucoes, setInstrucoes] = useState("");
  const [arquivos, setArquivos] = useState<Arquivo[]>([]);
  const [busy, setBusy] = useState(false);
  // A procedência por campo (ADR-023): de onde veio o texto que o agente escreveu.
  const [origens, setOrigens] = useState<Record<string, string[]>>({});
  const [erro, setErro] = useState<string | null>(null);

  /** A regra do NOME, aplicada a qualquer valor. Separada do bloqueio do passo porque ela também
   *  precisa valer sobre o que o AGENTE propõe, e uma segunda cópia divergiria. */
  const problemaNomeDe = useCallback(
    (valor: string): string | null => {
      const n = valor.trim();
      if (!n) return t("erroNomeVazio");
      if (!NOME_RECURSO.test(n)) return t("erroNomeFormato");
      if (n.length > 63) return t("erroNomeLongo");
      if (existentes.includes(n)) return t("erroNomeExiste", { name: n });
      return null;
    },
    [existentes, t],
  );

  /** O que impede de avançar, dito na hora — não no fim. */
  const problemaNome = useCallback((): string | null => {
    const doNome = problemaNomeDe(nome);
    if (doNome) return doNome;
    // O serviço exige descrição (o SDK a declara opcional, mas o Foundry recusa sem ela). Pedir
    // no passo 1 evita descobrir na publicação, depois de escrever instruções e anexar arquivos.
    if (!descricao.trim()) return t("erroDescricaoVazia");
    return null;
  }, [problemaNomeDe, nome, descricao, t]);

  /** A regra de cada campo que o agente pode propor — a mesma do formulário, não uma cópia. */
  const regraDoCampo = useCallback(
    (campo: string, valor: string): string | null => {
      if (campo === "name") return problemaNomeDe(valor);
      if (campo === "description" && !valor.trim()) return t("erroDescricaoVazia");
      return null;
    },
    [problemaNomeDe, t],
  );

  const addArquivos = (grupo: Grupo, lista: FileList | null) => {
    if (!lista?.length) return;
    setErro(null);
    void Promise.all(
      Array.from(lista).map(
        (f) =>
          new Promise<Arquivo | string>((resolve) => {
            const base = f.name.split("/").pop() ?? f.name;
            if (!nomeArquivoValido(base)) return resolve(t("erroArquivoNome", { name: f.name }));
            const reader = new FileReader();
            reader.onload = () =>
              resolve({ grupo, nome: base, conteudo: String(reader.result ?? "") });
            reader.onerror = () => resolve(t("erroArquivoLeitura", { name: base }));
            reader.readAsText(f);
          }),
      ),
    ).then((resultados) => {
      const bons = resultados.filter((r): r is Arquivo => typeof r !== "string");
      const ruins = resultados.filter((r): r is string => typeof r === "string");
      // Arquivo recusado é DITO, não descartado em silêncio: quem enviou 5 e viu 4 precisa saber
      // qual ficou de fora e por quê.
      if (ruins.length) setErro(ruins.join(" "));
      setArquivos((atual) => {
        const chave = (a: Arquivo) => `${a.grupo}/${a.nome}`;
        const mapa = new Map(atual.map((a) => [chave(a), a]));
        for (const a of bons) mapa.set(chave(a), a);
        return [...mapa.values()];
      });
    });
  };

  const remover = (grupo: Grupo, nomeArq: string) =>
    setArquivos((a) => a.filter((x) => !(x.grupo === grupo && x.nome === nomeArq)));

  /** O documento que vai ser enviado — mostrado no passo 4 antes de qualquer chamada. */
  const documento = (() => {
    const doc: Record<string, unknown> = {
      instructions: instrucoes.trim(),
      description: descricao.trim(),
    };
    // A procedência viaja com o recurso publicado (ADR-023): "de onde veio esta instrução" passa
    // a ter resposta no Foundry, não só na memória de quem estava na tela.
    const comOrigem = Object.entries(origens).filter(([, f]) => f.length);
    // Serializada: o Foundry exige valor de metadata em STRING (ver AgentWizard).
    if (comOrigem.length)
      doc.metadata = { provenance: JSON.stringify(Object.fromEntries(comOrigem)) };
    return doc;
  })();

  const publicar = async () => {
    setBusy(true);
    setErro(null);
    try {
      const alvo = `/api/foundry/skills/${encodeURIComponent(nome.trim())}`;

      // Primeiro a skill (inline), depois o bundle. A ordem importa: os arquivos são uma VERSÃO
      // da skill, então a skill precisa existir. Enviar o bundle primeiro criaria a skill sem as
      // instruções, que é o campo obrigatório.
      const r = await authedFetch(alvo, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: documento, default: true }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(body?.error ?? `HTTP ${r.status}`);
        return;
      }

      if (arquivos.length) {
        const form = new FormData();
        for (const a of arquivos) {
          // O grupo vira pasta: o serviço aceita upload de diretório e preserva o caminho.
          form.append("files", new Blob([a.conteudo]), `${a.grupo}/${a.nome}`);
        }
        const rf = await authedFetch(alvo, { method: "POST", body: form });
        const bf = await rf.json().catch(() => ({}));
        if (!rf.ok) {
          // A skill FOI criada; só o bundle falhou. Dizer as duas coisas evita que a pessoa
          // tente criar de novo e receba "já existe".
          setErro(t("erroBundle", { motivo: bf?.error ?? `HTTP ${rf.status}` }));
          onConcluido();
          return;
        }
      }
      onConcluido();
    } catch {
      setErro(tc("backendUnreachable"));
    } finally {
      setBusy(false);
    }
  };

  /** O que FALTA para avançar, ou null. Motivo em vez de booleano: um botão desabilitado sem
   *  explicação é um beco. A regra é "opcional nunca trava" — logo, o que trava é obrigatório e
   *  precisa se identificar. A etapa 3 (arquivos) é opcional e nunca bloqueia. */
  const faltaPara = (): string | null => {
    if (passo === 1) return problemaNome();
    if (passo === 2 && !instrucoes.trim()) return t("faltaInstrucoes");
    return null;
  };
  const bloqueio = faltaPara();
  const podeAvancar = bloqueio === null;

  /** Aplica a proposta aceita: valor no campo, fonte na procedência. Sempre os dois. */
  const aplicar = (p: FieldProposal) => {
    if (p.field === "instructions") setInstrucoes(p.value);
    else if (p.field === "description") setDescricao(p.value);
    else if (p.field === "name") setNome(p.value);
    setOrigens((o) => ({ ...o, [p.field]: p.sources }));
  };

  return (
    <section className="card stack-sm">
      {/* A tool vive enquanto o formulário está aberto — fechado, ela some, e o agente deixa de
          poder propor para um formulário que ninguém está vendo. */}
      <FieldProposalTool
        onAccept={aplicar}
        resource="skill"
        fields={["name", "description", "instructions"]}
        current={{ name: nome, description: descricao, instructions: instrucoes }}
        validate={regraDoCampo}
      />
      <header className="between">
        <h3 className="section-title">{t("title")}</h3>
        <button type="button" className="btn" disabled={busy} onClick={onCancelar}>
          {tc("cancel")}
        </button>
      </header>

      {/* Os quatro passos com nome: a pessoa vê onde está e quanto falta. */}
      <ol className="steps" aria-label={t("stepsLabel")}>
        {([1, 2, 3, 4] as const).map((p) => (
          <li key={p} className={`step ${passo === p ? "on" : passo > p ? "done" : ""}`}>
            <span className="step-num">{p}</span>
            <span className="step-label">{t(`step${p}`)}</span>
          </li>
        ))}
      </ol>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}

      {passo === 1 && (
        <div className="stack-sm">
          <input
            className="acct-btn"
            placeholder={t("namePlaceholder")}
            value={nome}
            disabled={busy}
            onChange={(e) => setNome(e.target.value)}
          />
          {/* O problema aparece enquanto digita, não ao tentar avançar. */}
          {nome.trim() && problemaNome() && <p className="t-xs bad-line">{problemaNome()}</p>}
          <p className="muted t-xs">{t("nameHelp")}</p>
          <input
            className="acct-btn"
            placeholder={t("descriptionPlaceholder")}
            value={descricao}
            disabled={busy}
            onChange={(e) => setDescricao(e.target.value)}
          />
        </div>
      )}

      {passo === 2 && (
        <div className="stack-sm">
          <p className="muted t-sm">{t("instructionsHelp")}</p>
          <AiField
            field="instructions"
            label={t("step2")}
            value={instrucoes}
            resource={t("resourceSkill")}
          >
            <textarea
              className="acct-btn"
              rows={10}
              placeholder={t("instructionsPlaceholder")}
              value={instrucoes}
              disabled={busy}
              onChange={(e) => setInstrucoes(e.target.value)}
            />
          </AiField>
        </div>
      )}

      {passo === 3 && (
        <div className="stack-sm">
          <p className="muted t-sm">{t("filesHelp")}</p>
          <div className="grid g2">
            {GRUPOS.map((g) => (
              <div key={g} className="stack-sm">
                <p className="t-xs strong">{t(`grupo_${g}`)}</p>
                <p className="muted t-xs">{t(`grupo_${g}_help`)}</p>
                <input
                  type="file"
                  multiple
                  className="acct-btn"
                  disabled={busy}
                  onChange={(e) => addArquivos(g, e.target.files)}
                />
                <ul className="file-list">
                  {arquivos
                    .filter((a) => a.grupo === g)
                    .map((a) => (
                      <li key={a.nome}>
                        <span className="t-mono t-xs">{a.nome}</span>
                        <button
                          type="button"
                          className="acct-btn"
                          disabled={busy}
                          onClick={() => remover(g, a.nome)}
                        >
                          {tc("delete")}
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="muted t-xs">{t("filesOptional")}</p>
        </div>
      )}

      {passo === 4 && (
        <div className="stack-sm">
          <p className="muted t-sm">{t("reviewHelp")}</p>
          <dl className="review">
            <dt>{t("reviewName")}</dt>
            <dd className="t-mono">{nome.trim()}</dd>
            <dt>{t("reviewFiles")}</dt>
            <dd>
              {arquivos.length
                ? GRUPOS.filter((g) => arquivos.some((a) => a.grupo === g))
                    .map((g) => `${t(`grupo_${g}`)}: ${arquivos.filter((a) => a.grupo === g).length}`)
                    .join(" · ")
                : t("reviewNoFiles")}
            </dd>
          </dl>
          {/* O documento exato que vai ser enviado — nada acontece sem a pessoa ver antes. */}
          <pre className="doc-preview">{JSON.stringify(documento, null, 2)}</pre>
        </div>
      )}

      <div className="row">
        {passo > 1 && (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => setPasso((p) => (p - 1) as 1 | 2 | 3)}
          >
            {t("back")}
          </button>
        )}
        <div className="grow" />
        {passo < 4 ? (
          <button
            type="button"
            className="btn btn-solid"
            disabled={busy || !podeAvancar}
            title={bloqueio ?? undefined}
            onClick={() => setPasso((p) => (p + 1) as 2 | 3 | 4)}
          >
            {t("next")}
          </button>
        ) : (
          <button type="button" className="btn btn-solid" disabled={busy} onClick={() => void publicar()}>
            {busy ? t("publishing") : t("publish")}
          </button>
        )}
      </div>
    </section>
  );
}
