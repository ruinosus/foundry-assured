#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ts from "typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const front = path.join(here, "..");
const source = readFileSync(path.join(front, "lib", "frontend-mode.ts"), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  fileName: "frontend-mode.ts",
});

let failures = 0;
function check(name, condition) {
  console.log(`${condition ? "OK   " : "FAIL "} ${name}`);
  if (!condition) failures++;
}

function loadModes(frontendMode, dataMode) {
  const previousFrontendMode = process.env.NEXT_PUBLIC_FRONTEND_MODE;
  const previousDataMode = process.env.NEXT_PUBLIC_DATA_MODE;

  if (frontendMode === undefined) delete process.env.NEXT_PUBLIC_FRONTEND_MODE;
  else process.env.NEXT_PUBLIC_FRONTEND_MODE = frontendMode;
  if (dataMode === undefined) delete process.env.NEXT_PUBLIC_DATA_MODE;
  else process.env.NEXT_PUBLIC_DATA_MODE = dataMode;

  const mod = { exports: {} };
  new Function("module", "exports", outputText)(mod, mod.exports);

  if (previousFrontendMode === undefined) delete process.env.NEXT_PUBLIC_FRONTEND_MODE;
  else process.env.NEXT_PUBLIC_FRONTEND_MODE = previousFrontendMode;
  if (previousDataMode === undefined) delete process.env.NEXT_PUBLIC_DATA_MODE;
  else process.env.NEXT_PUBLIC_DATA_MODE = previousDataMode;

  return mod.exports;
}

const defaults = loadModes(undefined, undefined);
check("legacy is the default frontend mode", defaults.frontendMode === "legacy");
check("connected is the default data mode", defaults.dataMode === "connected");
check("local indicator is disabled by default", defaults.isLocalDataMode === false);

const localAssured = loadModes("assured", "local");
check("assured mode is selectable", localAssured.frontendMode === "assured");
check("local mode enables the environment indicator", localAssured.isLocalDataMode === true);

const invalid = loadModes("other", "remote");
check("invalid frontend mode falls back to legacy", invalid.frontendMode === "legacy");
check("invalid data mode falls back to connected", invalid.dataMode === "connected");

const shell = readFileSync(path.join(front, "components", "shell", "AppShell.tsx"), "utf8");
check(
  "the local indicator is restricted to the assured shell",
  shell.includes('mode === "assured" && <EnvironmentBanner />'),
);

for (const file of ["package.json", "package-lock.json"]) {
  const manifest = readFileSync(path.join(front, file), "utf8");
  check(`${file} has no Rede Dor package`, !manifest.includes("@rededor/"));
}

console.log(failures ? `\n${failures} verification(s) failed.` : "\nAll verifications passed.");
process.exit(failures ? 1 : 0);
