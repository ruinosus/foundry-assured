// Os dois dicionários precisam ter exatamente as mesmas chaves.
//
// Uma chave presente só em pt-BR aparece como o próprio identificador na tela em inglês
// ("agents.emptyTitle" em vez do texto) — falha silenciosa que passa em qualquer build e só
// alguém abrindo aquela tela naquele idioma percebe.
import { readFileSync } from "node:fs";

const flat = (o, p = "") =>
  Object.entries(o).flatMap(([k, v]) =>
    v && typeof v === "object" ? flat(v, `${p}${k}.`) : [`${p}${k}`],
  );

// Valor por caminho, para comparar o CONTEÚDO de chaves que existem nos dois lados.
const leaves = (o, p = "", out = {}) => {
  for (const [k, v] of Object.entries(o)) {
    if (v && typeof v === "object") leaves(v, `${p}${k}.`, out);
    else out[`${p}${k}`] = v;
  }
  return out;
};
const holders = (v) =>
  typeof v === "string" ? [...v.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",") : "";

const dir = new URL("../apps/frontend/messages/", import.meta.url);
const locales = ["pt-BR", "en"];
const keys = Object.fromEntries(
  locales.map((l) => [l, new Set(flat(JSON.parse(readFileSync(new URL(`${l}.json`, dir), "utf8"))))]),
);

let bad = 0;
for (const a of locales) {
  for (const b of locales) {
    if (a === b) continue;
    const missing = [...keys[a]].filter((k) => !keys[b].has(k));
    if (missing.length) {
      bad += missing.length;
      console.error(`  ✗ faltam em ${b}: ${missing.join(", ")}`);
    }
  }
}
// Mesma chave nos dois idiomas, placeholders diferentes: a frase sai com `{produto}` cru no
// meio dela. Passa no build e na paridade de chaves — só esta comparação pega.
const vals = Object.fromEntries(locales.map((l) => [l, leaves(JSON.parse(readFileSync(new URL(`${l}.json`, dir), "utf8")))]));
for (const k of Object.keys(vals[locales[0]])) {
  if (!(k in vals[locales[1]])) continue;
  const [x, y] = locales.map((l) => holders(vals[l][k]));
  if (x !== y) {
    bad += 1;
    console.error(`  ✗ ${k}: placeholders divergem — [${x}] vs [${y}]`);
  }
}

if (bad) {
  console.error(`\n❌ ${bad} chave(s) sem par — a tela mostraria o identificador em vez do texto.`);
  process.exit(1);
}
console.log(`✅ dicionários em paridade (${keys["pt-BR"].size} chaves em ${locales.length} idiomas).`);

// ── Terceira verificação: toda chave USADA no código existe no dicionário ──────────────
//
// É o inverso das duas acima, e é a que pega o erro que aparece no navegador como
// "MISSING_MESSAGE: Could not resolve `x`". Paridade garante que os catálogos concordam;
// o detector garante que nenhum texto ficou fora deles; esta garante que nenhuma LEITURA
// aponta para uma chave que não existe — o que estoura em runtime, não no build.
//
// O namespace vem da declaração do hook no próprio arquivo (`const tc = useTranslations("common")`),
// então `tc("save")` é resolvido como `common.save`. Chave dinâmica (template com ${}) é anotada
// e conferida pelo PREFIXO: `td(`${d.id}.label`)` exige que algum `domains.*.label` exista.
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const FRONT = new URL("../apps/frontend/", import.meta.url).pathname;
const flatKeys = new Set(flat(JSON.parse(readFileSync(new URL("pt-BR.json", dir), "utf8"))));

function* walkTs(d) {
  for (const e of readdirSync(d)) {
    const f = join(d, e);
    if (statSync(f).isDirectory()) {
      if (e !== "node_modules" && e !== ".next") yield* walkTs(f);
    } else if (/\.tsx?$/.test(e)) yield f;
  }
}

const unresolved = [];
for (const sub of ["app", "components", "lib"]) {
  for (const file of walkTs(join(FRONT, sub))) {
    const src = readFileSync(file, "utf8");
    // Mapa variável → namespace, a partir das declarações do arquivo.
    const ns = {};
    for (const m of src.matchAll(/const\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\((?:\s*"([^"]*)"\s*)?\)/g)) {
      (ns[m[1]] ??= []).push(m[2] ?? "");
    }
    for (const m of src.matchAll(/\b(\w+)(?:\.rich|\.raw)?\(\s*(["'`])([^"'`]+)\2/g)) {
      const [, v, , key] = m;
      if (!(v in ns)) continue;
      const candidates = ns[v].map((n) => (n ? `${n}.${key}` : key));
      if (candidates.some((c) => flatKeys.has(c))) continue;
      const full = candidates[0];
      // Chave dinâmica: confere o prefixo estático antes do ${}.
      if (key.includes("${")) {
        const dynamicOk = candidates.some((cand) => {
          const prefix = cand.slice(0, cand.indexOf("${")).replace(/\.$/, "");
          if (prefix && [...flatKeys].some((k) => k.startsWith(prefix))) return true;
          // Sufixo depois do ${}: `domains.${id}.label` → procura qualquer *.label sob domains.
          const suffix = cand.slice(cand.lastIndexOf("}") + 1).replace(/^\./, "");
          const root = cand.slice(0, cand.indexOf(".${"));
          return Boolean(suffix) && [...flatKeys].some((k) => k.startsWith(root) && k.endsWith(`.${suffix}`));
        });
        if (dynamicOk) continue;
      }
      unresolved.push(`${relative(FRONT, file)} → ${full}`);
    }
  }
}

if (unresolved.length) {
  console.error(`\n  ✗ ${unresolved.length} leitura(s) apontando para chave inexistente:\n`);
  for (const u of [...new Set(unresolved)].sort()) console.error(`    ${u}`);
  console.error("\n  Isto estoura no navegador como MISSING_MESSAGE, não no build.\n");
  process.exit(1);
}
console.log("✅ toda chave usada no código existe no dicionário.");
