"use client";

// O RENDERIZADOR. Um componente, N manifestos.
//
// A PROPRIEDADE QUE ELE PRECISA TER, e que é o gate de sucesso desta camada:
//
//     não existe `if (campo.id === "instructions")` em lugar nenhum deste arquivo.
//
// O setter é derivado do `id` declarado. Trocar o manifesto troca o wizard inteiro — inclusive
// quais campos o agente pode escrever. Antes disto havia TRÊS componentes (agente, skill, base)
// com os mesmos campos escritos à mão em cada um; acrescentar uma validação num deles não
// acrescentava nos outros, e a diferença só aparecia quando alguém publicava pelo formulário que
// ainda não checava.
//
// O QUE CONTINUA SENDO CÓDIGO: os tipos de campo (abaixo) e os gates. Declarar um campo novo é
// dado; inventar um CONTROLE novo é uma entrada em `Controle` e um componente. É a linha que
// impede o manifesto de virar uma linguagem de programação pela porta dos fundos.
//
// O que este componente NÃO faz: publicar. Ele devolve os valores; quem monta o documento do
// serviço e chama a API é quem o usa — porque isso é específico do recurso, e é justamente o que
// o manifesto declara em `plan` mas não sabe executar.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { authedFetch } from "@/lib/auth/api";
import { AiField, AGENTE_DO_FORMULARIO } from "@/components/shell/AiField";
import { FieldProposalTool, type FieldProposal } from "@/components/shell/FieldProposal";
import { validarCampo, type RuleFailure } from "@/lib/formflow/rules";
import { revisao } from "@/lib/formflow/review";
import {
  campoVisivel,
  camposDe,
  valoresIniciais,
  type Campo,
  type FormFlowManifest,
  type Valores,
} from "@/lib/formflow/types";
import type { FieldOrigin } from "@/lib/okf";

/** O catálogo de um `choice`, e o que se soube ao tentar lê-lo.
 *
 *  LISTA VAZIA E FALHA DE LEITURA NÃO PODEM PARECER A MESMA COISA: "ainda não criei base nenhuma"
 *  leva a pessoa a criar uma; "não consegui ler as bases" leva a tentar de novo. Um select vazio
 *  calado faz alguém publicar sem base achando que não havia nenhuma. */
interface Catalogo {
  itens: string[];
  falhou: boolean;
}

/** Um arquivo anexado — nome E conteúdo.
 *
 *  O conteúdo vive FORA de `Valores` porque `Valores` é texto de formulário, e um arquivo de
 *  200 kB dentro do mesmo objeto que alimenta o diff e a revisão faria o motor carregar bytes que
 *  ele nunca usa. O que entra em `Valores[id]` é a lista de NOMES, que é o que a tela mostra e a
 *  revisão conta; o conteúdo sai daqui, na hora de publicar. */
export interface Anexo {
  nome: string;
  conteudo: string;
}

export interface FormFlowState {
  valores: Valores;
  /** Por campo `files`: os anexos com conteúdo, na ordem em que entraram. */
  anexos: Record<string, Anexo[]>;
  origens: Record<string, FieldOrigin>;
  /** O que impede de publicar, ou null. O MOTIVO, nunca um booleano: um botão desabilitado sem
   *  explicação é um beco. */
  bloqueio: string | null;
  /** Estado por seção, para o rail. */
  secoes: { id: string; titulo: string; pendencia: string | null; opcional: boolean; resumo: string }[];
  revisao: { label: string; texto: string }[];
}

export function useFormFlow(
  manifest: FormFlowManifest | null,
  opts: { taken?: string[]; inicial?: Valores } = {},
) {
  const t = useTranslations("formflow");
  // AS SEMENTES ENTRAM NO INICIALIZADOR, não num efeito.
  //
  // A primeira versão as aplicava com `setValores` dentro de um `useEffect([manifest])`, e isso
  // tem dois problemas — um que o lint aponta (render em cascata) e um pior, que ele não aponta:
  // o efeito roda DEPOIS da primeira pintura, então o formulário aparece por um quadro com os
  // campos vazios e o rail dizendo que falta preencher o que já está preenchido.
  //
  // O inicializador lazy resolve os dois porque o hook só é montado quando o manifesto existe —
  // quem chama devolve a tela de carregando antes disso. As sementes vêm do manifesto
  // (`initial:`) e do chamador (o rascunho do propositor, ADR-022), e o rascunho entra como VALOR
  // INICIAL de campo editável, nunca como algo já gravado: cada campo continua editável.
  const [valores, setValores] = useState<Valores>(() =>
    manifest ? { ...valoresIniciais(manifest), ...(opts.inicial ?? {}) } : {},
  );
  const [origens, setOrigens] = useState<Record<string, FieldOrigin>>({});
  const [anexos, setAnexos] = useState<Record<string, Anexo[]>>({});
  const [catalogos, setCatalogos] = useState<Record<string, Catalogo>>({});

  // Os catálogos que o manifesto declara. Um `fetch` por fonte distinta, em paralelo.
  useEffect(() => {
    if (!manifest) return;
    const fontes = new Map<string, string>();
    for (const c of camposDe(manifest)) if (c.catalog) fontes.set(c.catalog.source, c.catalog.key);
    if (!fontes.size) return;
    let vivo = true;
    void Promise.all(
      [...fontes].map(async ([source, key]) => {
        try {
          const r = await authedFetch(source, { cache: "no-store" });
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const b = await r.json();
          const bruto = (b?.[key] ?? []) as unknown[];
          const itens = bruto
            .map((x) => (typeof x === "string" ? x : String((x as { name?: string })?.name ?? "")))
            .filter(Boolean);
          return [source, { itens, falhou: false }] as const;
        } catch {
          return [source, { itens: [], falhou: true }] as const;
        }
      }),
    ).then((pares) => {
      if (vivo) setCatalogos(Object.fromEntries(pares));
    });
    return () => {
      vivo = false;
    };
  }, [manifest]);

  const traduzir = useCallback((f: RuleFailure | null): string | null => (f ? t(f.key, f.values) : null), [t]);

  /** A regra de um campo, pelo id. É ESTA função que o card de proposta usa — a mesma, não uma
   *  cópia: duas regras divergem, e a que diverge em silêncio é a do card. */
  const regraDoCampo = useCallback(
    (id: string, valor: string): string | null => {
      const campo = manifest ? camposDe(manifest).find((c) => c.id === id) : undefined;
      if (!campo) return null;
      return traduzir(validarCampo(valor, campo, { taken: opts.taken }));
    },
    [manifest, opts.taken, traduzir],
  );

  const set = useCallback((id: string, v: string | string[]) => {
    // O SETTER É DERIVADO DO ID. Não há um `aplicar()` com um `if` por campo — é o que faz
    // trocar de manifesto trocar o wizard inteiro.
    setValores((atual) => ({ ...atual, [id]: v }));
  }, []);

  /** Anexa arquivos a um campo `files`. Guarda o conteúdo e espelha os NOMES em `valores`, para
   *  que a revisão, o rail e a validação continuem enxergando um campo preenchido sem precisar
   *  saber que existe conteúdo em outro lugar. */
  const anexar = useCallback((id: string, novos: Anexo[]) => {
    setAnexos((atual) => {
      const antes = atual[id] ?? [];
      // Mesmo nome duas vezes é SUBSTITUIÇÃO, não duplicata: o serviço trata o caminho como
      // chave, e mandar dois `rollback.sh` deixaria o segundo vencer sem ninguém decidir isso.
      const mapa = new Map(antes.map((a) => [a.nome, a]));
      for (const n of novos) mapa.set(n.nome, n);
      const lista = [...mapa.values()];
      setValores((v) => ({ ...v, [id]: lista.map((a) => a.nome) }));
      return { ...atual, [id]: lista };
    });
  }, []);

  const desanexar = useCallback((id: string, nome: string) => {
    setAnexos((atual) => {
      const lista = (atual[id] ?? []).filter((a) => a.nome !== nome);
      setValores((v) => ({ ...v, [id]: lista.map((a) => a.nome) }));
      return { ...atual, [id]: lista };
    });
  }, []);

  const aplicarProposta = useCallback(
    (p: FieldProposal) => {
      set(p.field, p.value);
      // A origem INTEIRA: quem escreveu e quando entram junto das fontes, senão um campo escrito
      // pelo agente sem fonte ficaria indistinguível de um campo digitado à mão (lib/okf.ts).
      setOrigens((o) => ({
        ...o,
        [p.field]: { by: AGENTE_DO_FORMULARIO, at: new Date().toISOString(), sources: p.sources },
      }));
    },
    [set],
  );

  const estado: FormFlowState = useMemo(() => {
    if (!manifest) {
      return { valores, origens, anexos, bloqueio: null, secoes: [], revisao: [] };
    }
    const secoes = manifest.sections.map((s) => {
      const camposVisiveis = s.fields.filter((c) => campoVisivel(c, valores));
      // OPCIONAL NUNCA TRAVA — a regra está no manifesto (`optional: true`), não aqui.
      const pendencia = s.optional
        ? null
        : camposVisiveis
            .map((c) => traduzir(validarCampo(String(valores[c.id] ?? ""), c, { taken: opts.taken })))
            .find((x) => x) ?? null;
      const preenchidos = camposVisiveis
        .filter((c) => {
          const v = valores[c.id];
          return Array.isArray(v) ? v.length > 0 : !!String(v ?? "").trim();
        })
        .map((c) => c.label ?? c.id);
      return {
        id: s.id,
        titulo: s.title ?? s.id,
        pendencia,
        opcional: !!s.optional,
        resumo: preenchidos.length ? preenchidos.join(" · ") : t("secaoVazia"),
      };
    });
    return {
      valores,
      origens,
      anexos,
      bloqueio: secoes.map((s) => s.pendencia).find((x) => x) ?? null,
      secoes,
      revisao: revisao(manifest, valores, {
        semCapacidades: t("semCapacidades"),
        semArquivos: t("semArquivos"),
        comCapacidades: (lista) => t("comCapacidades", { list: lista }),
      }),
    };
  }, [manifest, valores, origens, anexos, opts.taken, traduzir, t]);

  return { estado, set, setValores, regraDoCampo, aplicarProposta, anexar, desanexar, catalogos };
}

/** O formulário renderizado a partir do manifesto. */
export function FormFlowFields({
  manifest,
  valores,
  set,
  regraDoCampo,
  catalogos,
  busy,
  origens,
  travadas,
  onAnexar,
  onDesanexar,
  onRecusar,
}: {
  manifest: FormFlowManifest;
  valores: Valores;
  set: (id: string, v: string | string[]) => void;
  regraDoCampo: (id: string, valor: string) => string | null;
  catalogos: Record<string, { itens: string[]; falhou: boolean }>;
  busy?: boolean;
  origens: Record<string, FieldOrigin>;
  /** Operações que ainda NÃO rodaram — uma seção com `lockedUntil` numa delas fica travada. */
  travadas?: string[];
  onAnexar?: (id: string, arquivos: Anexo[]) => void;
  onDesanexar?: (id: string, nome: string) => void;
  onRecusar?: (mensagem: string) => void;
}) {
  const t = useTranslations("formflow");
  return (
    <>
      {manifest.sections.map((s) => {
        const travada = !!s.lockedUntil && (travadas ?? []).includes(s.lockedUntil);
        return (
          <section key={s.id} id={`w-${s.id}`} className="wizard-section">
            <h4 className="wizard-section-title">
              {s.title ?? s.id}
              {s.optional && <span className="t-2xs muted-line">{t("opcional")}</span>}
            </h4>
            {s.help && <p className="muted t-sm">{s.help}</p>}
            {travada ? (
              <p className="t-xs muted-line">{s.lockedHelp ?? t("travada")}</p>
            ) : (
              <div className="stack-sm">
                {s.fields.filter((c) => campoVisivel(c, valores)).map((c) => (
                  <CampoRender
                    key={c.id}
                    campo={c}
                    valor={valores[c.id]}
                    set={set}
                    erro={regraDoCampo(c.id, String(valores[c.id] ?? ""))}
                    catalogo={c.catalog ? catalogos[c.catalog.source] : undefined}
                    busy={busy}
                    escritoPeloAgente={!!origens[c.id]}
                    onAnexar={onAnexar}
                    onDesanexar={onDesanexar}
                    onRecusar={onRecusar}
                    // A regra do NOME do arquivo é a do campo (`safeFilename`), aplicada na hora
                    // de anexar — não na publicação, quando já não dá para escolher outro.
                    onValidarNome={(nome) => regraDoCampo(c.id, nome)}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </>
  );
}

/** UM campo. O `switch` é por TIPO, nunca por id — é a diferença entre um renderizador e três
 *  wizards escritos à mão. */
function CampoRender({
  campo,
  valor,
  set,
  erro,
  catalogo,
  busy,
  escritoPeloAgente,
  onAnexar,
  onDesanexar,
  onValidarNome,
  onRecusar,
}: {
  campo: Campo;
  valor: string | string[] | undefined;
  set: (id: string, v: string | string[]) => void;
  erro: string | null;
  catalogo?: { itens: string[]; falhou: boolean };
  busy?: boolean;
  escritoPeloAgente: boolean;
  onAnexar?: (id: string, arquivos: Anexo[]) => void;
  onDesanexar?: (id: string, nome: string) => void;
  onValidarNome?: (nome: string) => string | null;
  onRecusar?: (mensagem: string) => void;
}) {
  const t = useTranslations("formflow");
  const texto = typeof valor === "string" ? valor : "";
  const lista = Array.isArray(valor) ? valor : [];
  const rotulo = campo.label ?? campo.id;

  // O controle. Sem `ai`, ele é o que se vê; com `ai`, o `AiField` o embrulha.
  let controle: ReactNode = null;
  switch (campo.type) {
    case "text":
    case "secret":
      controle = (
        <input
          className="acct-btn"
          type={campo.type === "secret" ? "password" : "text"}
          // O segredo não é lembrado pelo navegador: ele sai da memória quando a chamada termina,
          // e um gerenciador de senhas o guardaria depois disso.
          autoComplete={campo.type === "secret" ? "off" : undefined}
          placeholder={campo.placeholder}
          value={texto}
          disabled={busy}
          aria-label={rotulo}
          onChange={(e) => set(campo.id, e.target.value)}
        />
      );
      break;
    case "longtext":
      controle = (
        <textarea
          className="acct-btn"
          rows={campo.rows ?? 6}
          placeholder={campo.placeholder}
          value={texto}
          disabled={busy}
          aria-label={rotulo}
          onChange={(e) => set(campo.id, e.target.value)}
        />
      );
      break;
    case "choice": {
      const itens = campo.catalog ? (catalogo?.itens ?? []) : (campo.options ?? []);
      // Três estados, e os três são ditos: não carregou · carregou vazio · tem itens.
      if (campo.catalog && catalogo?.falhou) {
        controle = <p className="t-xs bad-line">{t("catalogoFalhou", { source: campo.catalog.source })}</p>;
      } else if (!itens.length) {
        controle = <p className="muted t-xs">{campo.emptyHelp ?? t("catalogoVazio")}</p>;
      } else {
        controle = (
          <select
            className="acct-btn"
            value={texto}
            disabled={busy}
            aria-label={rotulo}
            onChange={(e) => set(campo.id, e.target.value)}
          >
            <option value="">{t("nenhum")}</option>
            {itens.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        );
      }
      break;
    }
    case "multi": {
      // O `multi` aceita CATÁLOGO além de lista fixa, e é o que permite ao formulário do copiloto
      // oferecer os alvos derivados dos formulários reais em vez de uma lista escrita à mão.
      // Mesmos três estados do `choice`: não carregou · carregou vazio · tem itens.
      const opcoes = campo.catalog ? (catalogo?.itens ?? []) : (campo.options ?? []);
      if (campo.catalog && catalogo?.falhou) {
        controle = <p className="t-xs bad-line">{t("catalogoFalhou", { source: campo.catalog.source })}</p>;
        break;
      }
      if (!opcoes.length) {
        controle = <p className="muted t-xs">{campo.emptyHelp ?? t("catalogoVazio")}</p>;
        break;
      }
      controle = (
        <div className="row-tight">
          {opcoes.map((o) => (
            <label key={o} className="row-tight t-sm">
              <input
                type="checkbox"
                checked={lista.includes(o)}
                disabled={busy}
                onChange={() =>
                  set(campo.id, lista.includes(o) ? lista.filter((x) => x !== o) : [...lista, o])
                }
              />
              {o}
            </label>
          ))}
        </div>
      );
      break;
    }
    case "pair": {
      // Os dois pedaços só valem juntos (um MCP com rótulo e sem URL não é alcançável), então o
      // valor é UM: `rótulo\turl`. Meio preenchido é meio de nada.
      const [a = "", b = ""] = texto.split("\t");
      const juntar = (x: string, y: string) => (x || y ? `${x}\t${y}` : "");
      controle = (
        <div className="row-tight">
          {(campo.parts ?? []).map((p, i) => (
            <input
              key={p.id}
              className="acct-btn grow"
              placeholder={p.placeholder}
              value={i === 0 ? a : b}
              disabled={busy}
              aria-label={`${rotulo} · ${p.id}`}
              onChange={(e) => set(campo.id, i === 0 ? juntar(e.target.value, b) : juntar(a, e.target.value))}
            />
          ))}
        </div>
      );
      break;
    }
    case "files":
      controle = (
        <div className="stack-sm">
          <input
            type="file"
            multiple
            className="acct-btn"
            disabled={busy}
            aria-label={rotulo}
            onChange={(e) => {
              // O CONTEÚDO é lido aqui, não na publicação: o `File` do input vive enquanto o
              // elemento vive, e um formulário que só guardasse o nome descobriria isso no
              // momento de enviar — longe de onde dá para pedir o arquivo de novo.
              //
              // Nome de arquivo RECUSADO é dito, não descartado em silêncio: quem escolheu cinco
              // e viu quatro precisa saber qual ficou de fora e por quê. A regra é a do campo
              // (`safeFilename`), a mesma do backend.
              const escolhidos = Array.from(e.target.files ?? []);
              void Promise.all(
                escolhidos.map(
                  (f) =>
                    new Promise<{ nome: string; conteudo: string } | string>((resolve) => {
                      const nome = f.name.split("/").pop() ?? f.name;
                      const ruim = onValidarNome?.(nome);
                      if (ruim) return resolve(ruim);
                      const reader = new FileReader();
                      reader.onload = () => resolve({ nome, conteudo: String(reader.result ?? "") });
                      reader.onerror = () => resolve(`${nome}: ?`);
                      reader.readAsText(f);
                    }),
                ),
              ).then((rs) => {
                const bons = rs.filter((r): r is { nome: string; conteudo: string } => typeof r !== "string");
                const ruins = rs.filter((r): r is string => typeof r === "string");
                if (bons.length) onAnexar?.(campo.id, bons);
                if (ruins.length) onRecusar?.(ruins.join(" "));
              });
              // O input é limpo para que escolher o MESMO arquivo de novo dispare `change` — sem
              // isto, corrigir um arquivo e reanexá-lo não faz nada e parece que a tela travou.
              e.target.value = "";
            }}
          />
          {lista.length > 0 && (
            <ul className="file-list">
              {lista.map((n) => (
                <li key={n}>
                  <span className="t-xs">{n}</span>
                  <button
                    type="button"
                    className="acct-btn t-xs"
                    disabled={busy}
                    onClick={() => onDesanexar?.(campo.id, n)}
                  >
                    {t("remover")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      );
      break;
  }

  const corpo = campo.ai ? (
    <AiField field={campo.id} label={rotulo} value={texto} resource={t("recurso")}>
      {controle}
    </AiField>
  ) : (
    controle
  );

  return (
    <div className="stack-sm">
      <label className="t-xs strong">
        {rotulo}
        {campo.required && <span className="t-2xs muted-line"> · {t("obrigatorio")}</span>}
      </label>
      {corpo}
      {/* A VALIDAÇÃO APARECE NO CAMPO, enquanto se digita — e só depois de a pessoa ter escrito
          algo: reclamar de campo vazio que ela ainda não tocou é ruído. */}
      {erro && texto.trim() && <p className="t-xs bad-line">{erro}</p>}
      {!erro && texto.trim() && campo.type === "longtext" && (
        <p className="t-xs muted-line">
          {t("contagem", { count: texto.length })}
          {` · ${escritoPeloAgente ? t("escritoPeloAgente") : t("escritoPorVoce")}`}
        </p>
      )}
      {campo.help && <p className="muted t-xs">{campo.help}</p>}
    </div>
  );
}

/** A tool que o agente chama para propor um campo, ligada ao manifesto.
 *
 *  Os campos oferecidos são os que declaram `ai: true` — não uma lista escrita à mão. Um campo
 *  novo no documento passa a ser propositível sem tocar em código. */
export function FormFlowProposalTool({
  manifest,
  valores,
  regraDoCampo,
  onAccept,
}: {
  manifest: FormFlowManifest;
  valores: Valores;
  regraDoCampo: (id: string, valor: string) => string | null;
  onAccept: (p: FieldProposal) => void;
}) {
  const campos = camposDe(manifest).filter((c) => c.ai);
  return (
    <FieldProposalTool
      onAccept={onAccept}
      resource={manifest.name}
      fields={campos.map((c) => c.id)}
      current={Object.fromEntries(campos.map((c) => [c.id, String(valores[c.id] ?? "")]))}
      validate={regraDoCampo}
    />
  );
}
