// A revisão em prosa, derivada do manifesto.
//
// POR QUE ELA EXISTE. A última tela antes de algo acontecer no serviço era um JSON cru. Ele é
// legível para quem escreve SDK — e quem escreve SDK não precisa deste produto. Quem publica
// precisa saber o que o recurso VAI e NÃO VAI poder fazer, em português.
//
// O texto vem do bloco `review:` do manifesto, não daqui: trocar a frase é editar o documento.
// Este arquivo só sabe interpolar e contar.

import type { FormFlowManifest, LinhaRevisao, Valores } from "@/lib/formflow/types";

export interface LinhaResolvida {
  label: string;
  texto: string;
}

/** O valor de um campo como texto, para interpolar. Lista vira lista separada por vírgula. */
function comoTexto(v: string | string[] | undefined): string {
  if (Array.isArray(v)) return v.join(", ");
  return (v ?? "").trim();
}

/** Substitui `{campo}` pelos valores. Um campo vazio vira travessão em vez de sumir: a linha
 *  "Vai criar o agente  e a sua primeira versão" tem um buraco onde deveria ter uma pergunta. */
function interpolar(template: string, valores: Valores): string {
  return template.replace(/\{(\w+)\}/g, (_, k) => comoTexto(valores[k]) || "—");
}

/** As linhas da revisão, prontas para a tela.
 *
 *  `vazio` é o que dizer quando uma linha derivada não tem nada a mostrar — vem da tela porque é
 *  texto traduzido, e o manifesto não carrega traduções. */
export function revisao(
  m: FormFlowManifest,
  valores: Valores,
  vazio: { semCapacidades: string; semArquivos: string; comCapacidades: (lista: string) => string },
): LinhaResolvida[] {
  const linhas: LinhaResolvida[] = [];
  for (const l of m.review ?? []) {
    linhas.push({ label: l.label, texto: resolver(l, m, valores, vazio) });
  }
  return linhas;
}

function resolver(
  l: LinhaRevisao,
  m: FormFlowManifest,
  valores: Valores,
  vazio: { semCapacidades: string; semArquivos: string; comCapacidades: (lista: string) => string },
): string {
  if (l.const) return l.const;

  // As capacidades são uma LISTA DINÂMICA, não um template: quantas e quais depende do que a
  // pessoa marcou, e um `{tools} {mcp}` produziria "code_interpreter " com um espaço solto
  // quando não há MCP.
  //
  // QUAIS CAMPOS SÃO CAPACIDADE VEM DO MANIFESTO (`fields:`), não do TIPO deles. A primeira
  // versão varria todo `choice`/`multi`/`pair` — o que acerta no formulário do agente (onde
  // `choice` é base e toolbox) e ERRA feio no do copiloto, onde `choice` é `mount` e `runtime`:
  // a revisão dizia "vai poder escrever: dock lateral, backend". Visto rodando a tela.
  //
  // Sem `fields:` a linha não presume nada — volta ao comportamento antigo apenas quando o
  // manifesto pede, o que mantém os manifestos existentes funcionando sem herdar o erro.
  if (l.fromCapabilities) {
    const declarados = l.fields;
    const campos = m.sections
      .flatMap((s) => s.fields)
      .filter((c) => (declarados ? declarados.includes(c.id) : ["multi", "choice", "pair"].includes(c.type)));
    const partes: string[] = [];
    for (const c of campos) {
      const v = valores[c.id];
      if (Array.isArray(v)) partes.push(...v);
      else if (typeof v === "string" && v.trim()) partes.push(v.trim());
    }
    return partes.length ? vazio.comCapacidades(partes.join(", ")) : vazio.semCapacidades;
  }

  if (l.fromFiles) {
    const contagens = m.sections
      .flatMap((s) => s.fields)
      .filter((c) => c.type === "files")
      .map((c) => ({ label: c.label ?? c.id, n: (valores[c.id] as string[] | undefined)?.length ?? 0 }))
      .filter((x) => x.n > 0);
    if (!contagens.length) return vazio.semArquivos;
    return contagens.map((x) => `${x.label}: ${x.n}`).join(" · ");
  }

  // `variant` é uma frase ALTERNATIVA, não um sufixo: sem base, a resposta não tem fonte, e isso
  // é uma afirmação diferente — não a mesma frase com um pedaço a menos. O CAMPO que a governa
  // vem do manifesto (`when`), nunca de um nome escrito aqui.
  if (l.variant && comoTexto(valores[l.variant.when])) {
    return interpolar(l.variant.then, valores);
  }
  return l.from ? interpolar(l.from, valores) : "";
}
