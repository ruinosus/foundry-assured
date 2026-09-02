#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const front = path.join(here, "..");
const matrix = JSON.parse(readFileSync(path.join(front, "route-parity.json"), "utf8"));

let failures = 0;
function check(name, condition, detail = "") {
  if (condition) return;
  console.log(`FAIL ${name}${detail ? ` - ${detail}` : ""}`);
  failures++;
}

function pageFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) return pageFiles(absolute);
    return entry.name === "page.tsx" ? [path.relative(front, absolute)] : [];
  });
}

function routeFromComponent(component) {
  const relative = component.replace(/^app\/?/, "").replace(/(^|\/)page\.tsx$/, "");
  return relative ? `/${relative}` : "/";
}

const pages = pageFiles(path.join(front, "app")).sort();
const routes = matrix.routes.map((entry) => entry.route).sort();
const discoveredRoutes = pages.map(routeFromComponent).sort();
const requiredEvidence = new Set(matrix.requiredEvidence);
const allowedStates = new Set([
  "loading",
  "empty",
  "error",
  "partial",
  "no-permission",
  "stale",
  "awaiting-human",
  "success",
  "redirect",
]);

check("matrix version is pinned", matrix.version === 1);
check("legacy and assured modes are covered", JSON.stringify(matrix.modes) === JSON.stringify(["legacy", "assured"]));
check("every page has one matrix row", JSON.stringify(routes) === JSON.stringify(discoveredRoutes), `${routes.length}/${discoveredRoutes.length}`);
check("matrix routes are unique", new Set(routes).size === routes.length);

for (const entry of matrix.routes) {
  const componentPath = path.join(front, entry.component);
  const surfacePath = entry.surface === "redirect" ? null : path.join(front, entry.surface);
  const source = existsSync(componentPath) ? readFileSync(componentPath, "utf8") : "";
  const label = entry.route;

  check(`${label} component exists`, existsSync(componentPath), entry.component);
  check(`${label} surface exists`, entry.surface === "redirect" || existsSync(surfacePath), entry.surface);
  check(`${label} preserves legacy route`, entry.legacy === entry.route);
  check(`${label} declares actions`, Array.isArray(entry.actions) && entry.actions.length > 0);
  check(`${label} declares roles`, Array.isArray(entry.roles) && entry.roles.length > 0);
  check(`${label} declares known states`, entry.states.length > 0 && entry.states.every((state) => allowedStates.has(state)));
  check(`${label} has responsive and keyboard evidence`, [...requiredEvidence].every((item) => entry.evidence.includes(item)));

  if (entry.surface === "redirect") {
    check(`${label} uses a server redirect`, source.includes("redirect("));
    check(`${label} redirects to assured destination`, source.includes(`redirect(\"${entry.assured}\")`), entry.assured);
  } else {
    check(`${label} is wrapped by AppShell`, source.includes("<AppShell"));
    check(`${label} keeps the same assured URL`, entry.assured === entry.route);
  }
}

const families = new Map();
for (const entry of matrix.routes) {
  const states = families.get(entry.family) ?? new Set();
  entry.states.forEach((state) => states.add(state));
  families.set(entry.family, states);
}
for (const [family, states] of families) {
  if (family === "redirects" || family === "overview") continue;
  for (const state of ["loading", "error", "success"]) {
    check(`${family} family covers ${state}`, states.has(state));
  }
}

console.log(failures ? `\n${failures} route parity verification(s) failed.` : `\nRoute parity verified for ${routes.length} pages.`);
process.exit(failures ? 1 : 0);
