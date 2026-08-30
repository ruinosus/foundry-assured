// As regras que um campo pode citar pelo NOME, no manifesto.
//
// POR QUE NOMES, E NÃO CÓDIGO NO MANIFESTO. Um manifesto que carregasse expressões seria uma
// linguagem de programação entrando pela porta dos fundos: quem escreve o documento passaria a
// precisar de um interpretador, e o que ele declara deixaria de ser auditável por leitura. O
// manifesto cita `resourceName`; quem sabe o que isso significa é este arquivo.
//
// O VOCABULÁRIO É FECHADO, e é a razão de existir um gate de espelho. Uma regra com nome errado
// — `resourceNames`, com "s" — carrega sem erro e simplesmente não é aplicada: o campo passa a
// aceitar qualquer coisa, e ninguém descobre até o serviço recusar a publicação. O backend guarda
// a mesma lista em `tests/formflow/manifest_test.py`, e o gate falha se as duas divergirem.
//
// A regra devolve o MOTIVO, nunca um booleano: um campo inválido sem explicação é um beco, e a
// mensagem é o que a pessoa lê para saber o que corrigir. As mensagens são chaves de tradução —
// quem as resolve é a tela, com `useTranslations`.

/** O que uma regra sabe sobre o resto do formulário quando precisa julgar. */
export interface RuleContext {
  /** Nomes já usados no serviço — `unique` compara contra eles. */
  taken?: string[];
}

/** Uma falha: a chave de tradução e os valores que ela interpola. */
export interface RuleFailure {
  key: string;
  values?: Record<string, string | number>;
}

export type Rule = (value: string, ctx: RuleContext) => RuleFailure | null;

const NOME_RECURSO = /^[a-z0-9]+(-[a-z0-9]+)*$/;
// Mesma regra do backend (`_safe_blob_name`): sem barra, sem `..`, sem ponto inicial.
const NOME_ARQUIVO = /^[a-zA-Z0-9._-]+$/;

export const REGRAS: Record<string, Rule> = {
  /** Nome de recurso do Foundry: minúsculas, números e hífens no meio. */
  resourceName: (v) =>
    NOME_RECURSO.test(v.trim()) ? null : { key: "rule_resourceName" },

  /** O serviço corta em 63 caracteres. Pedir aqui evita a viagem até o Azure. */
  max63: (v) => (v.trim().length <= 63 ? null : { key: "rule_max63" }),

  /** Nome já usado.
   *
   *  NÃO é erro de digitação, e a mensagem diz isso: publicar com um nome existente cria uma
   *  VERSÃO NOVA do recurso que já existe, que é outra operação. Dizer no campo evita a surpresa
   *  na revisão. */
  unique: (v, ctx) =>
    (ctx.taken ?? []).includes(v.trim()) ? { key: "rule_unique", values: { name: v.trim() } } : null,

  /** Nome de arquivo que não atravessa diretório — o serviço trata `/` como hierarquia. */
  safeFilename: (v) => {
    const n = v.trim();
    const seguro =
      !!n && !n.includes("/") && !n.includes("..") && !n.startsWith(".") && NOME_ARQUIVO.test(n);
    return seguro ? null : { key: "rule_safeFilename", values: { name: n } };
  },
};

/** Aplica as regras de um campo, na ordem declarada, e para na primeira falha.
 *
 *  PARA NA PRIMEIRA de propósito: mostrar "o nome tem maiúsculas E passa de 63 caracteres E já
 *  existe" faz a pessoa corrigir três coisas para descobrir a quarta. Uma por vez é mais rápido.
 *
 *  `required` é tratado ANTES das regras e não é uma delas: um campo obrigatório vazio tem uma
 *  mensagem própria, e rodar `resourceName` sobre a string vazia diria "use minúsculas" para
 *  quem não escreveu nada. */
export function validarCampo(
  valor: string,
  campo: { required?: boolean; rules?: string[] },
  ctx: RuleContext = {},
): RuleFailure | null {
  const v = valor ?? "";
  if (!v.trim()) return campo.required ? { key: "rule_required" } : null;
  for (const nome of campo.rules ?? []) {
    const regra = REGRAS[nome];
    // Regra desconhecida FALA. Ignorar em silêncio é exatamente o modo de falha que o gate de
    // espelho existe para impedir — e se um manifesto chegar aqui com um nome que este arquivo
    // não conhece, a tela precisa dizer, não fingir que validou.
    if (!regra) return { key: "rule_unknown", values: { rule: nome } };
    const falha = regra(v, ctx);
    if (falha) return falha;
  }
  return null;
}
