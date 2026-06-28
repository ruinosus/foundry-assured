Contexto do repositório — fatos extraídos dos arquivos fornecidos:

- package.json: nome "foundry-helpdesk-frontend", versão "0.1.0". (package.json)
- package.json: scripts definidos:
  - dev: "next dev"
  - build: "next build"
  - start: "next start"
  - lint: "next lint"
  - typecheck: "tsc --noEmit"
  - demo: "bash ../../scripts/demo.sh"
  - demo:record: "bash ../../scripts/demo-record.sh"
  (package.json)
- package.json: dependências listadas (com versões):
  - "@ag-ui/client": "^0.0.57"
  - "@azure/msal-browser": "^5.15.0"
  - "@azure/msal-react": "^5.5.0"
  - "@copilotkit/react-core": "^1.61.2"
  - "@copilotkit/react-ui": "^1.61.2"
  - "@copilotkit/runtime": "^1.61.2"
  - "next": "^15.5.0"
  - "react": "^19.0.0"
  - "react-dom": "^19.0.0"
  (package.json)
- package.json: devDependencies listadas (com versões):
  - "@copilotkit/aimock": "^1.34.0"
  - "@types/node": "^22.0.0"
  - "@types/react": "^19.0.0"
  - "@types/react-dom": "^19.0.0"
  - "typescript": "^5.6.0"
  (package.json)

- next.config.ts: export default com opção output: "standalone". (next.config.ts)

- tsconfig.json: compilerOptions e outras configurações presentes, incluindo:
  - target: "ES2022"
  - lib: ["dom", "dom.iterable", "esnext"]
  - allowJs: true
  - skipLibCheck: true
  - strict: true
  - noEmit: true
  - esModuleInterop: true
  - module: "esnext"
  - moduleResolution: "bundler"
  - resolveJsonModule: true
  - isolatedModules: true
  - jsx: "preserve"
  - incremental: true
  - plugins: [{ "name": "next" }]
  - paths: { "@/*": ["./*"] }
  - include: ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"]
  - exclude: ["node_modules"]
  (tsconfig.json)

- lib/branding.ts: export const branding com as propriedades:
  - product: "Foundry Helpdesk"
  - tagline: "Engineering support"
  - description: "Internal engineering support concierge"
  - assistant: "Concierge"
  (lib/branding.ts)

- lib/auth/msal.ts:
  - Lê as variáveis de ambiente NEXT_PUBLIC_ENTRA_TENANT_ID, NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID e NEXT_PUBLIC_ENTRA_API_CLIENT_ID em tenantId, spaClientId e apiClientId. (lib/auth/msal.ts)
  - Importa demoMode de "@/lib/demo". (lib/auth/msal.ts)
  - Exporta authConfigured calculado como !demoMode && Boolean(tenantId && spaClientId && apiClientId). (lib/auth/msal.ts)
  - Exporta apiScopes como apiClientId ? [`api://${apiClientId}/access_as_user`] : []. (lib/auth/msal.ts)
  - Quando authConfigured é verdadeiro, constrói um objeto config que inclui auth.clientId, auth.authority usando o tenantId, auth.redirectUri (window.location.origin quando window definido) e cache.cacheLocation = "sessionStorage". (lib/auth/msal.ts)
  - Exporta msalInstance que é new PublicClientApplication(config) apenas quando config está definido e typeof window !== "undefined"; caso contrário msalInstance é null. (lib/auth/msal.ts)

- lib/auth/api.ts:
  - Exporta a função authedFetch(input, init = {}) que importa apiScopes, authConfigured e msalInstance de "@/lib/auth/msal". (lib/auth/api.ts)
  - A função cria Headers a partir de init.headers; se authConfigured e msalInstance estão definidos, obtém a primeira conta com msalInstance.getAllAccounts()[0]; se houver conta, tenta msalInstance.acquireTokenSilent({ scopes: apiScopes, account }) e, em caso de sucesso, define o header "Authorization" para "Bearer " + r.accessToken; em caso de erro no acquireTokenSilent, não seta o header e continua. (lib/auth/api.ts)
  - A função retorna fetch(input, { ...init, headers }). (lib/auth/api.ts)
  - O comentário no arquivo indica que, em dev local (authConfigured=false), a função degrada para um fetch simples. (lib/auth/api.ts)