// O merge de cabeçalhos não pode produzir a MESMA chave em caixas diferentes.
//
// POR QUE ISTO EXISTE. `Authorization` e `authorization` são chaves DIFERENTES num objeto
// JavaScript e IGUAIS num header HTTP. Quando as duas sobrevivem ao spread, o `Headers` do fetch
// normaliza e COMBINA os valores com vírgula — `Bearer A, Bearer B` — que é um header de
// autorização inválido. O backend responde 401.
//
// MEDIDO: 13 de 13 chamadas a `/conversations/by-id` falhavam assim, e a tela abria a conversa
// vazia sem dizer por quê. Passou despercebido porque enquanto o handler NÃO repassava o token
// existia uma chave só; o repasse — acrescentado para consertar um 401 — foi o que criou a
// duplicata.
import { readFileSync } from "node:fs";

const ARQUIVO = "app/api/copilotkit/[[...slug]]/route.ts";
let falhas = 0;
const check = (nome, ok) => { console.log(`  ${ok ? "ok  " : "FALHA"} ${nome}`); if (!ok) falhas++; };

// 1. o mecanismo, provado no runtime real — não numa reimplementação
const combinado = new Headers({ Authorization: "Bearer AAA", authorization: "Bearer BBB" });
check("o fetch COMBINA chaves que diferem só na caixa",
  combinado.get("authorization") === "Bearer AAA, Bearer BBB");

const norm = {};
for (const [k, v] of Object.entries({ Authorization: "Bearer AAA", authorization: "Bearer BBB" })) {
  norm[k.toLowerCase()] = v;
}
check("normalizar para minúsculo deixa um valor só",
  new Headers(norm).get("authorization") === "Bearer BBB");

// 2. o código entregue normaliza antes de repassar
const fonte = readFileSync(ARQUIVO, "utf8");
check("o handler normaliza a caixa das chaves antes do fetch",
  /toLowerCase\(\)\]\s*=\s*v/.test(fonte));
check("não sobrou spread ingênuo dos dois conjuntos de cabeçalho",
  !/\{\s*\.\.\.this\.headers,\s*\.\.\.\(request\.headers\s*\?\?\s*\{\}\)\s*\}\s*;/.test(fonte));

console.log();
if (falhas) { console.log(`FALHOU: ${falhas} verificação(ões)`); process.exit(1); }
console.log("tudo certo");
