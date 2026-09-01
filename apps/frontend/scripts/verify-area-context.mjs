import { readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const front = path.resolve(import.meta.dirname, "..");
const read = (relative) => readFileSync(path.join(front, relative), "utf8");
const requireText = (source, text, message) => {
  if (!source.includes(text)) throw new Error(message);
};

const identity = read("lib/auth/roles.ts");
const selector = read("components/shell/AreaSelector.tsx");
const shell = read("components/shell/AppShell.tsx");
const fetchApi = read("lib/auth/api.ts");
const proxy = read("app/api/tenant/[...path]/route.ts");
const admin = read("components/admin/Areas.tsx");

requireText(identity, 'authedFetch("/api/me")', "A identidade e as áreas devem vir de /api/me.");
requireText(selector, "areas.some((area) => area.id ===", "O seletor deve validar a escolha contra areas[].");
requireText(shell, 'mode === "assured" && <AreaSelector', "O seletor deve existir somente no shell assured.");
requireText(fetchApi, 'headers.set("X-Area-ID", areaId)', "authedFetch deve enviar X-Area-ID.");
requireText(proxy, 'req.headers.get("x-area-id")', "O proxy deve encaminhar X-Area-ID.");
requireText(proxy, 'req.headers.get("if-match")', "O proxy deve encaminhar If-Match.");
requireText(proxy, "export async function PATCH", "O proxy tenant deve aceitar PATCH.");
requireText(admin, 'headers: { "If-Match":', "A edição deve usar If-Match.");
requireText(admin, 'status: area.status === "active" ? "suspended" : "active"', "A tela deve suspender em vez de excluir áreas.");
if (admin.includes('method: "DELETE"')) throw new Error("Áreas não podem ter exclusão física.");

process.stdout.write("area context frontend: 10 invariantes aprovados\n");
