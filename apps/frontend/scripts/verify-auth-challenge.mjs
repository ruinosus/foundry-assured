import assert from "node:assert/strict";
import fs from "node:fs";

const proxy = fs.readFileSync("app/api/authoring/[...path]/route.ts", "utf8");
const auth = fs.readFileSync("lib/auth/api.ts", "utf8");
const workspace = fs.readFileSync("components/bundles/BundleWorkspace.tsx", "utf8");

assert.match(proxy, /response\.headers\.get\("www-authenticate"\)/);
assert.match(proxy, /responseHeaders\.set\("WWW-Authenticate", challenge\)/);
assert.match(auth, /error=\"insufficient_claims\"/);
assert.match(auth, /acquireTokenSilent\(request\)/);
assert.match(auth, /acquireTokenPopup\(request\)/);
assert.match(auth, /headers\.set\("Authorization", `Bearer \$\{steppedUpToken\}`\)/);
assert.match(workspace, /if \(status !== 401\) setToolApproval\(null\)/);

console.log("auth claims challenge contract: PASS");