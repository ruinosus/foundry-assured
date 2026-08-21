// O app e o CopilotKit têm de resolver a MESMA cópia de streamdown.
//
// `MessageEvidence.tsx` importa `defaultRehypePlugins` de "streamdown" e entrega a lista ao
// renderer do CopilotKit. Isso só funciona enquanto os dois resolvem a mesma cópia — e o npm
// resolve por RANGE, não por intenção. Em 2026-08-20 o dependabot subiu a declaração do app de
// `^1.6.11` para `^2.5.0` (major); o CopilotKit continuou em `^1.3.0` e ganhou uma cópia
// aninhada. Passaram a existir DUAS: o app montava os plugins na 2.5.0 e o renderer 1.6.11 os
// recebia. Nada quebrou no build, nada apareceu no typecheck, e o Mermaid parou de renderizar.
//
// O próprio `MessageEvidence.tsx:40-46` já documenta um episódio igual com duas cópias de
// `unified`. É um modo de falha recorrente deste app, e ele não se anuncia: o sintoma aparece
// no render, longe da causa.
//
//     node scripts/check-renderer-single-copy.mjs
import { readFileSync } from "node:fs";

// SÓ `streamdown`, de propósito. É o pacote cujo `defaultRehypePlugins` NÓS importamos e
// entregamos ao renderer da lib — o único onde "duas cópias" vira comportamento errado em vez
// de só peso em disco. `unified` também tem cópias divergentes (10.1.2 na raiz, 11.0.5 sob as
// libs), mas isso é PRÉ-EXISTENTE e já está contornado: `MessageEvidence.tsx` deriva o tipo de
// `StreamdownProps` em vez de importar de `unified`. Incluí-lo aqui faria o gate nascer
// vermelho por algo conhecido e resolvido — e um gate assim é desligado, não obedecido.
const PACOTES = ["streamdown"];
const lock = JSON.parse(readFileSync("apps/frontend/package-lock.json", "utf8"));

let falhou = false;
for (const pacote of PACOTES) {
  const copias = Object.entries(lock.packages ?? {})
    .filter(([caminho]) => caminho.endsWith(`node_modules/${pacote}`))
    .map(([caminho, meta]) => ({ caminho, versao: meta.version }));

  if (copias.length <= 1) {
    const v = copias[0]?.versao ?? "(ausente)";
    console.log(`✅ ${pacote}: uma cópia (${v})`);
    continue;
  }
  falhou = true;
  console.log(`❌ ${pacote}: ${copias.length} cópias — o app e o renderer podem divergir`);
  for (const c of copias) console.log(`   ${c.versao.padEnd(10)} ${c.caminho}`);
}

if (falhou) {
  console.log(
    "\n   Alinhe o range em apps/frontend/package.json com o que o CopilotKit resolve" +
      "\n   (`npm ls streamdown` mostra quem pede o quê). Uma cópia aninhada significa que" +
      "\n   `import from \"<pacote>\"` no nosso código NÃO é o mesmo módulo que a lib usa."
  );
  process.exit(1);
}
