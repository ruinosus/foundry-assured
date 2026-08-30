// A procedência no vocabulário do **OKF v0.2** — a spec aberta do Google Cloud.
//
// POR QUE TROCAR UM FORMATO QUE FUNCIONAVA. O que gravávamos era
//
//     metadata.provenance = '{"description":["rh-politicas"]}'
//
// um mapa campo → lista de fontes, inventado aqui. Ele responde "de onde veio" e mais nada, e
// isso deixa três perguntas sem resposta no recurso publicado:
//
//   * um campo que o agente escreveu SEM fonte e um campo que a pessoa digitou sozinha ficam
//     indistinguíveis — os dois somem do mapa. É a diferença entre "o modelo escreveu do próprio
//     conhecimento" (honesto, e o prompt permite) e "ninguém escreveu isto com IA";
//   * QUANDO o texto foi escrito não viaja;
//   * QUEM o escreveu não viaja.
//
// O OKF v0.2 já nomeia as três (`generated`, `sources`, `verified`), é vendor-neutral, e este
// repositório já é produtor OKF — `openwiki/index.md` declara `okf_version`. Adotar o vocabulário
// da spec em vez de manter o nosso é a MÁXIMA MAIOR aplicada a formato: existe padrão publicado,
// ele cobre o caso, e o nosso não ficava melhor por ser nosso.
//
// O QUE NÃO ENTRA AQUI, E POR QUÊ. O OKF define um terceiro campo, `verified: [{by, at}]`, de
// onde o consumidor deriva o trust tier pelo prefixo `human:`. Ele é gravado no BACKEND, na
// trilha, e não neste documento — porque `by` é a identidade de quem revisou, e o documento
// publicado é um recurso compartilhado. É a mesma regra que mantém o nome do aprovador fora da
// mensagem do chat: a identidade pertence à trilha de auditoria (ADR-023, I-10). O backend usa
// `actor()`, que já devolve `human:<e-mail>` — a convenção de ator do OKF, por coincidência feliz.
//
// Referência: https://github.com/GoogleCloudPlatform/open-knowledge-format (SPEC §5.1–5.3)

/** Um material de que o campo deriva. `resource` é o único obrigatório na spec. */
export interface OkfSource {
  id: string;
  resource: string;
}

/** Quem produziu o texto, e quando. A spec chama isto de "actor convention" (§7):
 *  `<producer>/<version>` para agente ou ferramenta. */
export interface OkfGenerated {
  by: string;
  at: string;
}

export interface OkfFieldProvenance {
  generated: OkfGenerated;
  sources?: OkfSource[];
}

export interface OkfProvenance {
  okf_version: "0.2";
  fields: Record<string, OkfFieldProvenance>;
}

/** O que o formulário acumula enquanto a pessoa decide: por campo, quem propôs e com que fontes. */
export interface FieldOrigin {
  /** O agente que propôs. Sem `/versão` de propósito: a tela conhece o NOME do agente do dock,
   *  não a versão do modelo que o atendeu. A spec aceita o produtor sozinho, e um número de
   *  versão inventado seria pior que um ausente. */
  by: string;
  /** ISO 8601 com offset explícito — exigência da spec para todo campo de data. */
  at: string;
  sources: string[];
}

/** Monta o bloco de procedência. Devolve `null` quando nenhum campo tem origem: um bloco vazio
 *  no metadata diria "declarei procedência" sobre um documento inteiramente escrito à mão. */
export function buildProvenance(origins: Record<string, FieldOrigin>): OkfProvenance | null {
  const fields: Record<string, OkfFieldProvenance> = {};
  for (const [field, o] of Object.entries(origins)) {
    fields[field] = {
      generated: { by: o.by, at: o.at },
      // `sources` ausente quando vazio, nunca `[]`: a spec trata campo ausente como "não
      // declarado", e uma lista vazia diria "derivei de nada", que é outra afirmação.
      ...(o.sources.length
        ? { sources: o.sources.map((s) => ({ id: slugify(s), resource: s })) }
        : {}),
    };
  }
  return Object.keys(fields).length ? { okf_version: "0.2", fields } : null;
}

/** O `id` de uma fonte: estável, e é a chave que a spec usa para atribuição por claim
 *  (`[^id]` em footnote). Derivado do `resource` para não pedir à tela um dado que ela não tem. */
function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 63) || "source"
  );
}

/** A procedência serializada, como o Foundry exige.
 *
 *  O SERVIÇO EXIGE STRING nos valores de `metadata` — um objeto é recusado com
 *  `The JSON value could not be converted to System.String`, medido publicando. Isso não mudou
 *  com o OKF: o que mudou foi o CONTEÚDO da string. */
export function serializeProvenance(origins: Record<string, FieldOrigin>): string | null {
  const p = buildProvenance(origins);
  return p ? JSON.stringify(p) : null;
}
