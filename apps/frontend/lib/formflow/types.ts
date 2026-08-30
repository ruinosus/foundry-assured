// A forma de um manifesto de FormFlow, como a tela o consome.
//
// O documento é `apps/backend/agents/assured/flows/<nome>.md` — markdown com frontmatter OKF
// (`type: formflow`) e o `spec` num bloco YAML no corpo. O backend serve o `spec` já parseado em
// `GET /flows/<nome>`; estes tipos descrevem o que chega.
//
// O TIPO DE CAMPO É CÓDIGO, O CAMPO É DADO. Declarar um campo novo é editar o documento;
// inventar um CONTROLE novo (um seletor de data, um editor de tabela) é escrever um componente e
// acrescentá-lo a `TipoCampo` aqui. É a linha que impede o manifesto de virar uma linguagem de
// programação pela porta dos fundos — e ela está escrita no gate do backend, que recusa um tipo
// que a tela não conhece.

export type TipoCampo =
  | "text"
  | "longtext"
  | "choice" // um valor de uma lista, que pode vir de um catálogo do serviço
  | "multi" // vários de uma lista fixa
  | "pair" // dois campos que só valem juntos (rótulo + URL de um MCP)
  | "files" // arquivos anexados, lidos no browser
  | "secret"; // não persiste, some da memória quando a chamada termina

/** De onde a lista de um `choice` vem, quando não é fixa.
 *
 *  A LISTA VEM DO SERVIÇO, NÃO DO MANIFESTO: duas listas do mesmo recurso divergem no primeiro
 *  item novo, e a que diverge em silêncio é a da tela (SEGUNDA MÁXIMA). O manifesto diz ONDE
 *  buscar; o que existe é o serviço quem sabe. */
export interface Catalogo {
  source: string;
  /** A chave do array dentro da resposta (`{"bases": [...]}` → `bases`). */
  key: string;
}

export interface Campo {
  id: string;
  label?: string;
  type: TipoCampo;
  required?: boolean;
  /** O agente pode propor este campo. Só faz sentido em campo de texto — o gate do backend
   *  recusa `ai: true` em qualquer outro. */
  ai?: boolean;
  placeholder?: string;
  help?: string;
  /** O que dizer quando o catálogo volta VAZIO — que é diferente de não ter carregado. */
  emptyHelp?: string;
  rules?: string[];
  options?: string[];
  catalog?: Catalogo;
  initial?: string;
  rows?: number;
  parts?: { id: string; placeholder?: string }[];
  /** `false` = o valor não sobrevive à chamada (o token de leitura de repositório). */
  retain?: boolean;
}

export interface Secao {
  id: string;
  title?: string;
  help?: string;
  /** Opcional NUNCA trava — a regra do produto, declarada no manifesto em vez de escrita no
   *  componente. */
  optional?: boolean;
  /** A seção fica travada até a operação nomeada rodar (o container da base vem do nome). */
  lockedUntil?: string;
  lockedHelp?: string;
  fields: Campo[];
}

/** Uma linha da revisão em prosa. `from` interpola valores do formulário; `const` é texto fixo. */
export interface LinhaRevisao {
  label: string;
  from?: string;
  /** Uma frase ALTERNATIVA, usada quando o campo nomeado em `when` está preenchido.
   *
   *  O CAMPO É DECLARADO, não presumido: a primeira versão perguntava por `valores.knowledge_base`
   *  direto no motor — um `if` por nome de campo escondido dentro do renderizador, exatamente o
   *  que esta camada existe para não ter. Com `when`, o manifesto diz de quem a frase depende. */
  variant?: { when: string; then: string };
  const?: string;
  /** Derivada das capacidades marcadas, em vez de um template: a lista é dinâmica. */
  fromCapabilities?: boolean;
  /** Derivada dos arquivos anexados. */
  fromFiles?: boolean;
}

/** Uma operação do plano de publicação. */
export interface Operacao {
  id: string;
  title?: string;
  method?: string;
  path?: string;
  encoding?: string;
  /** Operações que precisam ter rodado antes. A DEPENDÊNCIA É DADO — e o gate do backend prova
   *  que ela aponta para uma operação que existe. */
  requires?: string[];
  /** O que acontece quando ESTA falha depois de a anterior ter dado certo. */
  onFailure?: string;
  approval?: { required?: boolean; role?: string; because?: string };
  note?: string;
}

export interface FormFlowManifest {
  name: string;
  /** Onde a procedência viaja, ou `null` quando o contrato do recurso não tem onde recebê-la. */
  provenance?: string | null;
  provenanceNote?: string;
  sections: Secao[];
  review?: LinhaRevisao[];
  plan?: Operacao[];
}

/** Os valores do formulário. Tudo string ou lista de string: o manifesto descreve um formulário,
 *  e formulário é texto — a conversão para o documento do serviço é de quem publica. */
export type Valores = Record<string, string | string[]>;

/** Todos os campos, achatados, na ordem em que aparecem. */
export function camposDe(m: FormFlowManifest): Campo[] {
  return m.sections.flatMap((s) => s.fields);
}

/** Os valores iniciais que o manifesto declara em `initial:`. */
export function valoresIniciais(m: FormFlowManifest): Valores {
  const v: Valores = {};
  for (const c of camposDe(m)) if (typeof c.initial === "string") v[c.id] = c.initial;
  return v;
}
