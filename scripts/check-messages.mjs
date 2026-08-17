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
if (bad) {
  console.error(`\n❌ ${bad} chave(s) sem par — a tela mostraria o identificador em vez do texto.`);
  process.exit(1);
}
console.log(`✅ dicionários em paridade (${keys["pt-BR"].size} chaves em ${locales.length} idiomas).`);
