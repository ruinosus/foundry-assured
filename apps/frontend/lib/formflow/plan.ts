// O EXECUTOR DO PLANO DE PUBLICAÇÃO.
//
// POR QUE ELE EXISTE. `plan` já era dado declarado no manifesto — com `requires`, `approval` e
// `onFailure` — e ninguém o executava. O resultado é que três coisas que o documento declara
// ficavam inertes: a seção travada até uma operação rodar, a dependência entre operações, e o que
// dizer quando a segunda falha com a primeira já feita.
//
// A FALHA PARCIAL É O MOTIVO REAL DESTE ARQUIVO. Publicar uma skill são DUAS chamadas: criar a
// skill, depois subir o bundle de arquivos. Quando a segunda falha, a skill EXISTE. Uma tela que
// diz só "erro" faz a pessoa tentar de novo — e a segunda tentativa falha na primeira operação,
// agora por nome duplicado, com uma mensagem que não tem nada a ver com o problema. Ela precisa
// ouvir as duas coisas: o que deu certo, e o que não deu.
//
// O que este módulo NÃO faz: montar o corpo da requisição. Isso é específico do recurso — o
// manifesto declara que existe um `POST /api/foundry/skills/{name}`, e não sabe (nem deveria) o
// que vai dentro. Quem chama fornece o corpo por operação.

import type { Operacao, Valores } from "@/lib/formflow/types";

/** O que aconteceu com uma operação. */
export type StatusOperacao = "pendente" | "rodando" | "feita" | "falhou" | "pulada";

export interface ResultadoOperacao {
  id: string;
  status: StatusOperacao;
  /** A mensagem do serviço, quando falhou. */
  erro?: string;
}

export interface ResultadoPlano {
  operacoes: ResultadoOperacao[];
  /** As que rodaram com sucesso — é isto que destrava uma seção com `lockedUntil`. */
  feitas: string[];
  /** true quando ALGUMA operação teve sucesso e alguma falhou. O caso que a tela precisa
   *  distinguir de "nada aconteceu". */
  parcial: boolean;
}

/** Como o chamador executa UMA operação. Devolve o erro, ou null em caso de sucesso.
 *
 *  Devolver o erro em vez de lançar é deliberado: um `throw` no meio de um plano de três passos
 *  perde o que já tinha dado certo, que é justamente a informação que a falha parcial precisa. */
export type Executor = (op: Operacao, valores: Valores) => Promise<string | null>;

/** Substitui `{campo}` no caminho pelos valores — `/api/foundry/skills/{name}`. */
export function resolverPath(op: Operacao, valores: Valores): string {
  return (op.path ?? "").replace(/\{(\w+)\}/g, (_, k) => encodeURIComponent(String(valores[k] ?? "")));
}

/** As operações que ainda NÃO rodaram — o que uma seção `lockedUntil` consulta. */
export function pendentes(plano: Operacao[], feitas: string[]): string[] {
  return plano.map((o) => o.id).filter((id) => !feitas.includes(id));
}

/** Executa o plano na ordem declarada, respeitando `requires`.
 *
 *  UMA OPERAÇÃO CUJA DEPENDÊNCIA FALHOU É `pulada`, NUNCA `falhou`. A distinção não é cosmética:
 *  "não rodou porque a anterior não rodou" e "rodou e deu erro" levam a ações diferentes, e
 *  achatar as duas em "falhou" faria a pessoa procurar um problema onde não houve nenhum.
 *
 *  E o plano PARA na primeira falha de uma operação de que outras dependem — seguir adiante
 *  chamaria o serviço com um recurso que não existe, trocando um erro claro por um obscuro.
 *
 *  `selecionadas` limita quais operações rodam: o manifesto do `knowledge` declara `upload_files`
 *  E `import_repo`, e a pessoa escolhe um dos dois caminhos — declarar as duas não significa
 *  executar as duas. */
export async function executarPlano(
  plano: Operacao[],
  valores: Valores,
  executor: Executor,
  opts: { selecionadas?: string[]; feitas?: string[] } = {},
): Promise<ResultadoPlano> {
  const alvo = opts.selecionadas ?? plano.map((o) => o.id);
  const feitas = [...(opts.feitas ?? [])];
  const operacoes: ResultadoOperacao[] = [];
  let houveFalha = false;

  for (const op of plano) {
    if (!alvo.includes(op.id)) continue;
    if (feitas.includes(op.id)) {
      // Já rodou numa tentativa anterior. Não roda de novo: a segunda chamada de `create_skill`
      // falharia por nome duplicado, com uma mensagem que não tem relação com o problema real.
      operacoes.push({ id: op.id, status: "feita" });
      continue;
    }
    const faltando = (op.requires ?? []).filter((r) => !feitas.includes(r));
    if (faltando.length) {
      operacoes.push({ id: op.id, status: "pulada" });
      continue;
    }
    const erro = await executor(op, valores);
    if (erro) {
      operacoes.push({ id: op.id, status: "falhou", erro });
      houveFalha = true;
      continue;
    }
    feitas.push(op.id);
    operacoes.push({ id: op.id, status: "feita" });
  }

  return {
    operacoes,
    feitas,
    // PARCIAL é "alguma coisa ficou de pé E alguma coisa não". Só falhas, ou só sucessos, não é
    // parcial — e é a diferença entre "tente de novo" e "não tente de novo do zero".
    parcial: houveFalha && feitas.length > 0,
  };
}
