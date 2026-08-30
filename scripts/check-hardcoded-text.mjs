// Encontra texto humano cravado no código, fora dos dicionários.
//
// Este gate existe porque o anterior não bastava. `check-messages.mjs` compara pt-BR com en e
// garante PARIDADE — nenhuma chave existe num idioma só. Mas paridade não é COBERTURA: uma
// string que nunca virou chave está ausente dos dois arquivos, e a comparação entre eles passa
// tranquila. Foi exatamente assim que a tela de visão geral ficou em português fixo depois de
// eu declarar a tradução completa.
//
// A heurística procura o que um humano leria: duas ou mais palavras, ao menos uma com 3+ letras,
// em texto de JSX, em literais de arrays de dados e nos atributos que chegam aos olhos
// (title, placeholder, aria-label). O que é técnico fica de fora por lista explícita — nome de
// campo do portal do Azure, comando de CLI, classe CSS, rota. Traduzir esses seria pior:
// alguém procuraria "referência do Cofre de Chaves" num portal onde está escrito
// "Key Vault reference".

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("../apps/frontend/", import.meta.url).pathname;
const DIRS = ["app", "components", "lib"];

// `app/api/` é servidor, não interface: o que sai de lá é resposta HTTP para o nosso próprio
// cliente, e quem mostra texto ao usuário é o componente, com a chave dele.
const SKIP_PATH = /^app\/api\//;

// Termos que devem permanecer em inglês mesmo na interface em português: são nomes de coisas
// que a pessoa vai procurar no portal do Foundry, no código ou no terminal.
const TECHNICAL = [
  /^[a-z][a-z0-9_]*$/, // identificador: create_ticket, gpt-5-mini
  /^(uv|npm|az|azd|bicep|curl|python) /, // comando de terminal
  /key vault|foundry|azure|entra|oauth|obo|mcp|sse|ag-ui|http|api\b|kb\b|acl|rbac|hitl/i,
  /^[A-Z_]{3,}$/, // CONSTANTE_ASSIM
  /^\/|^https?:|^@\/|\.(tsx?|css|json|yaml|md)$/, // rota, url, import, arquivo
];

// Fragmento de código que o regex capturou por acidente (casou o fim de uma string com o começo
// da seguinte), diretiva do Next, valor de CSS ou tipo do TypeScript. Nada disso é interface.
const NOT_TEXT = [
  /^use (client|server)$/,
  /[{}<>]|=>|\$\{|\w+\(|^,|: \w+\.\w+/,
  /^\d|px |#[0-9a-f]{3,8}\b|\b(solid|rgba?|var|calc|flex|grid)\b/i,
  /\|\s*\w+$/, // união de tipos: void | Promise
  /^\(|prefers-color-scheme|^:scope|ease-out|ease-in|\b\d*\.?\d+m?s\b/, // media query, seletor, transição
  /^(case|default|return|export|import|type|const|let|var|await|yield)\b/, // sintaxe, não frase
];

const isTechnical = (s) =>
  TECHNICAL.some((re) => re.test(s)) || NOT_TEXT.some((re) => re.test(s));

// Duas palavras, ao menos uma com 3+ letras (inclui acentos). "OK" não é frase; "Abrir agente" é.
const looksHuman = (s) => {
  const words = s.trim().split(/\s+/).filter((w) => /[a-zA-ZÀ-ÿ]/.test(w));
  return words.length >= 2 && words.some((w) => w.replace(/[^a-zA-ZÀ-ÿ]/g, "").length >= 3);
};

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== "node_modules" && entry !== ".next") yield* walk(full);
    } else if (/\.tsx?$/.test(entry)) {
      yield full;
    }
  }
}

const findings = [];

for (const file of [...DIRS].flatMap((d) => [...walk(join(ROOT, d))])) {
  const src = readFileSync(file, "utf8");
  const rel = relative(ROOT, file);
  if (SKIP_PATH.test(rel)) continue;

  // Um arquivo que GERA formato externo (YAML de workflow, template de outra ferramenta) contém
  // palavras que são contrato daquele formato, não texto de tela — traduzi-las quebraria a saída.
  // A marca viaja com o arquivo; uma lista de caminhos aqui ficaria desatualizada no primeiro
  // rename.
  if (src.includes("@gera-formato-externo")) continue;

  let inBlock = false;
  src.split("\n").forEach((line, i) => {
    // Marcador de LINHA, para o caso que o de arquivo não cobre: um componente que tem texto de
    // TELA (traduzível) e texto para o MODELO no mesmo arquivo — descrição de schema de tool,
    // motivo devolvido numa chamada. Marcar o arquivo inteiro ali deixaria texto de tela futuro
    // passar em silêncio, que é o oposto do que este gate faz.
    if (line.includes("@texto-para-modelo")) return;
    // Mensagem de CONSOLE não é interface: ela é escrita para quem depura, em qualquer idioma
    // que o time depure. Regra estrutural em vez de marcador porque ela não pode ser abusada —
    // não se renderiza tela a partir de `console.error`, então o que passa por aqui não é texto
    // que o usuário vá ler.
    if (/\bconsole\.(log|warn|error|info|debug)\s*\(/.test(line)) return;
    // Comentário não é interface — nem o de linha, nem o bloco, nem o {/* */} do JSX.
    if (inBlock) {
      if (line.includes("*/")) inBlock = false;
      return;
    }
    if (/\{?\/\*/.test(line) && !line.includes("*/")) {
      inBlock = true;
      return;
    }
    const code = line
      .replace(/\{?\/\*.*?\*\/\}?/g, "")
      .replace(/^\s*(\/\/|\*).*$/, "")
      // Comentário no FIM da linha também não é interface. `(?<!:)` preserva `https://`.
      .replace(/(?<!:)\/\/.*$/, "");
    if (!code.trim()) return;
    // Uma linha que já consulta o dicionário está resolvida.
    if (/\bt\w*\(["'`]/.test(code)) return;

    const candidates = [];

    // 1. Literais de string — cobre arrays de dados e ternários, que o grep de JSX não via.
    for (const m of code.matchAll(/(["'])((?:(?!\1)[^\\]|\\.){4,120})\1/g)) {
      const before = code.slice(Math.max(0, m.index - 24), m.index);
      // Fora: import, className, e chaves de objeto de configuração técnica.
      if (/(from|import|className|classList|require|cookie|setAttribute|getItem|setItem)\s*[=(:]?\s*$/.test(before)) continue;
      candidates.push(m[2]);
    }

    // 2. Texto entre tags JSX, inclusive colado em emoji (`💬 Abrir um agente`) e misturado
    //    com expressões (`{c.source} — documento interno`): a expressão sai, o texto fica.
    for (const m of code.matchAll(/>([^<>\n]{4,160})</g)) {
      candidates.push(m[1].replace(/\{[^{}]*\}/g, " "));
    }
    // 3. Linha solta de texto dentro de JSX — não abre nem fecha tag, mas é o que se lê na
    //    tela. Propriedade de objeto (`id: "helpdesk",`) não conta: tem `:` ou fecha em vírgula.
    const bare = code.trim();
    if (!/[<>={}();]/.test(bare) && !/^["'\w-]+\s*:/.test(bare) && !/,$/.test(bare)) {
      candidates.push(bare);
    }

    for (const text of candidates) {
      const clean = text.replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, "").trim();
      if (!clean || isTechnical(clean) || !looksHuman(clean)) continue;
      findings.push({ file: rel, line: i + 1, text: clean.slice(0, 72) });
    }
  });
}

if (findings.length) {
  console.error(`\n  ${findings.length} strings de interface fora do dicionário:\n`);
  let last = "";
  for (const f of findings) {
    if (f.file !== last) console.error(`  ${f.file}`);
    last = f.file;
    console.error(`    ${String(f.line).padStart(4)}  ${f.text}`);
  }
  console.error(`\n  Mova para messages/*.json e leia com useTranslations().\n`);
  process.exit(1);
}

console.log("  nenhuma string de interface fora do dicionário");
