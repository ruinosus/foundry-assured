# Changelog

## [0.10.0](https://github.com/ruinosus/foundry-assured/compare/v0.9.0...v0.10.0) (2026-08-21)


### Features

* **backend:** a recuperação com ACL vira ContextProvider — e o helpdesk ganha ACL que não tinha ([#167](https://github.com/ruinosus/foundry-assured/issues/167)) ([f3fb460](https://github.com/ruinosus/foundry-assured/commit/f3fb4601fef2bc5e5b40f202c160b34dd0a14536))
* **backend:** o preço vem da Azure, o modelo de valor vira documento, e FOCUS espera volume (ADR-024) ([#164](https://github.com/ruinosus/foundry-assured/issues/164)) ([ec4ef03](https://github.com/ruinosus/foundry-assured/commit/ec4ef0369eb96b09a3eb16b39a40692130f1f968))
* **backend:** um ponto de entrada por runtime, a mesma contabilidade (passos 1–3) ([#166](https://github.com/ruinosus/foundry-assured/issues/166)) ([5284a92](https://github.com/ruinosus/foundry-assured/commit/5284a926554919508b9de3ec7ccc08da56f5bc33))
* **docs:** as oito páginas anteriores adotam o sistema visual novo ([#196](https://github.com/ruinosus/foundry-assured/issues/196)) ([cad8613](https://github.com/ruinosus/foundry-assured/commit/cad86130ea243dd7c44cc043c4d7f68de65d14a0))
* **frontend:** conversa na URL e compartilhamento por link ([#183](https://github.com/ruinosus/foundry-assured/issues/183)) ([55804f4](https://github.com/ruinosus/foundry-assured/commit/55804f4fdb74dc4f4cca8cf4e7d9d4917c386567))
* **grounded:** o domínio pode responder como AGENTE PUBLICADO — atrás de uma chave ([#172](https://github.com/ruinosus/foundry-assured/issues/172)) ([8e5fef8](https://github.com/ruinosus/foundry-assured/commit/8e5fef809b476602ff31f4821f13e5bb18b64830))
* **helpdesk:** o painel de evidências passa a funcionar — por API pública, sem monkeypatch ([#171](https://github.com/ruinosus/foundry-assured/issues/171)) ([cf7d63b](https://github.com/ruinosus/foundry-assured/commit/cf7d63b947ae32171d334c4845811e316d602281))
* monolito modular, camada de evidência e a medição de uso fechada (ADR-017..023) ([#163](https://github.com/ruinosus/foundry-assured/issues/163)) ([bc8816b](https://github.com/ruinosus/foundry-assured/commit/bc8816b25bdda0fb43f2e078c3eb1b23444cd5e3))
* **techdocs:** o domínio ganha corpus próprio, recortado do selfwiki em três níveis ([#194](https://github.com/ruinosus/foundry-assured/issues/194)) ([b6174cd](https://github.com/ruinosus/foundry-assured/commit/b6174cd7ea58caca1ae32dd88d50a7e84afa05fd))
* **tooling:** a camada de aceleradores encontra três listas duplicadas, e o import-linter volta a vigiar ([#197](https://github.com/ruinosus/foundry-assured/issues/197)) ([bc65336](https://github.com/ruinosus/foundry-assured/commit/bc653367a4c710244d54e05a678ad6a6480a3b3c))


### Bug Fixes

* **backend:** /oncall e /deepcall serviam sem autenticação — e o gate que impede a volta ([#165](https://github.com/ruinosus/foundry-assured/issues/165)) ([d40d6ad](https://github.com/ruinosus/foundry-assured/commit/d40d6ad5e9562691072a2138f97ae86c3a3a870e))
* **backend:** shared mode could not boot with auth on, and would have leaked config between tenants ([#156](https://github.com/ruinosus/foundry-assured/issues/156)) ([4259539](https://github.com/ruinosus/foundry-assured/commit/4259539e711b8d2524f8d77964c588a33110d390))
* **ci:** o header de identidade do Search leva o token cru, não `Bearer` ([#191](https://github.com/ruinosus/foundry-assured/issues/191)) ([c65d800](https://github.com/ruinosus/foundry-assured/commit/c65d80089f10ebc67ef84152658ebf563f1dca67))
* **ci:** o verificador do selfwiki prova o trim com duas identidades reais ([#193](https://github.com/ruinosus/foundry-assured/issues/193)) ([cbb63a6](https://github.com/ruinosus/foundry-assured/commit/cbb63a6e8b3977f99005dcaf338600b7a3afe950))
* **ci:** repair the module paths ADR-017 broke in workflows and scripts ([#155](https://github.com/ruinosus/foundry-assured/issues/155)) ([08e078d](https://github.com/ruinosus/foundry-assured/commit/08e078d7f2b6febbc5135f0b7928b5a204c667e3))
* **ci:** trocar leitura elevada por identidade real no verificador do ingest-selfwiki ([#177](https://github.com/ruinosus/foundry-assured/issues/177)) ([73c8b7b](https://github.com/ruinosus/foundry-assured/commit/73c8b7b9cc13870246a48e3ed84f32f87ca581e7))
* **docs:** a landing do Pages apontava para dois lugares que não existem ([#190](https://github.com/ruinosus/foundry-assured/issues/190)) ([c7c1050](https://github.com/ruinosus/foundry-assured/commit/c7c1050057cbb235a3b07c15d2a2b9f5fe82535b))
* **docs:** as páginas publicadas voltam a descrever o que o projeto é hoje ([#195](https://github.com/ruinosus/foundry-assured/issues/195)) ([8606990](https://github.com/ruinosus/foundry-assured/commit/860699050140a1213b12802f6bdb271f8dc23a75))
* **eval:** o gate de atualidade da wiki não opina sem histórico ([#174](https://github.com/ruinosus/foundry-assured/issues/174)) ([d7b87a1](https://github.com/ruinosus/foundry-assured/commit/d7b87a1ede04931e16ab568ba4f0defd40573d77))
* **eval:** the wiki-freshness gate could never be satisfied ([#159](https://github.com/ruinosus/foundry-assured/issues/159)) ([7a052ca](https://github.com/ruinosus/foundry-assured/commit/7a052ca4cffd2e68bde66f4b0461276af951622c))
* **frontend:** a evidência fica legível e para de ocupar a tela ([#180](https://github.com/ruinosus/foundry-assured/issues/180)) ([8f56ded](https://github.com/ruinosus/foundry-assured/commit/8f56dedb2d294099b7891a2374518953c60cc084))
* **frontend:** mesclar cabeçalhos sem duplicar a caixa da chave ([#182](https://github.com/ruinosus/foundry-assured/issues/182)) ([9fc7c41](https://github.com/ruinosus/foundry-assured/commit/9fc7c412ddff9b75a5ad427fadcb30c69533b8b7))
* **frontend:** o rótulo Fontes usa a cor do texto ([#181](https://github.com/ruinosus/foundry-assured/issues/181)) ([c6edfbf](https://github.com/ruinosus/foundry-assured/commit/c6edfbf78e0333a106322d8a5f8f8a4669e6bf2c))
* **infra:** a identidade do app ganha a role de storage que nunca teve ([#201](https://github.com/ruinosus/foundry-assured/issues/201)) ([f6ae4c8](https://github.com/ruinosus/foundry-assured/commit/f6ae4c8edb3dd932f168c136de38496d124c8bf8))
* **infra:** as variáveis que o backend precisa nunca chegavam ao container publicado ([#199](https://github.com/ruinosus/foundry-assured/issues/199)) ([007f399](https://github.com/ruinosus/foundry-assured/commit/007f39938a276f93b11dd61f7189176c51d8bd52))
* **infra:** ligar isVersioningEnabled no blobService para viabilizar imutabilidade da ADR-023 ([#179](https://github.com/ruinosus/foundry-assured/issues/179)) ([1a2f185](https://github.com/ruinosus/foundry-assured/commit/1a2f1856e91803fad6aeb3208c74ae34df3eb817))
* **infra:** resolve AZURE_CI_PRINCIPAL_ID no CI e falha o deploy se as roles de dado sumirem ([#178](https://github.com/ruinosus/foundry-assured/issues/178)) ([ac813b0](https://github.com/ruinosus/foundry-assured/commit/ac813b094366f1dae67d5ba734da78aecf0a4dd8))
* **infra:** um clone novo consegue subir o backend ([#189](https://github.com/ruinosus/foundry-assured/issues/189)) ([8304fe9](https://github.com/ruinosus/foundry-assured/commit/8304fe9c0c9aae147e5fa1b840bea522faa75b3a))
* **knowledge:** o carimbo de ACL parava de valer sozinho, por uma agenda que ninguém pediu ([#198](https://github.com/ruinosus/foundry-assured/issues/198)) ([7990dc6](https://github.com/ruinosus/foundry-assured/commit/7990dc629e2ecfc148ad4ea51153f8d6a47f3cd7))
* o Mermaid volta a renderizar — duas causas, uma de versão e uma de prompt ([#200](https://github.com/ruinosus/foundry-assured/issues/200)) ([01f3deb](https://github.com/ruinosus/foundry-assured/commit/01f3debc2c6feaa07b242ac02893406cb0571b06))
* **registry:** o gate de espelho passa a ler o domains.ts que o nome dele promete ([#202](https://github.com/ruinosus/foundry-assured/issues/202)) ([395b42b](https://github.com/ruinosus/foundry-assured/commit/395b42b1c720b756f8ba383f16315991e7b63b79))
* **wiki:** a regeneração poda a geração anterior ([#176](https://github.com/ruinosus/foundry-assured/issues/176)) ([3ca1472](https://github.com/ruinosus/foundry-assured/commit/3ca147202ceeb5ed0618b8b5eddeb67a6a2d6b07))
* **wiki:** the citation contract still asked for per-area scope ([#151](https://github.com/ruinosus/foundry-assured/issues/151)) ([4b749e7](https://github.com/ruinosus/foundry-assured/commit/4b749e7bac56789f0b1097cd4a8212b5c5c65d05))


### Refactors

* as citações passam a falar o vocabulário do framework ([#169](https://github.com/ruinosus/foundry-assured/issues/169)) ([e21bad1](https://github.com/ruinosus/foundry-assured/commit/e21bad1be450de50b12679b652395ad14b9d63f0))
* **backend:** modular monolith by domain, with the boundaries checked in CI (ADR-017/018) ([#154](https://github.com/ruinosus/foundry-assured/issues/154)) ([3f9968f](https://github.com/ruinosus/foundry-assured/commit/3f9968f43ee9a292f4b70707cac3736679387356))
* rename the cockpit domain to techdocs, and drop the internal references ([#161](https://github.com/ruinosus/foundry-assured/issues/161)) ([44ae19f](https://github.com/ruinosus/foundry-assured/commit/44ae19f38b6a4fd19dadfe77aea9fb52c3b4c21c))
* tirar `cockpit` de tudo que é superfície viva ([#192](https://github.com/ruinosus/foundry-assured/issues/192)) ([f15e927](https://github.com/ruinosus/foundry-assured/commit/f15e927aef620dc0b9b90c40832043e443a801da))


### Documentation

* **adr:** ADR-025 — o vocabulário de citação é do framework; o transporte fica nosso ([#170](https://github.com/ruinosus/foundry-assured/issues/170)) ([84506cb](https://github.com/ruinosus/foundry-assured/commit/84506cbd5aae7eabddfe764825500c64a7e6d011))
* **backend:** OBSERVABILITY.md, and a boot comment that stopped being true ([#157](https://github.com/ruinosus/foundry-assured/issues/157)) ([77636f0](https://github.com/ruinosus/foundry-assured/commit/77636f0d86ce2f09d10b4d600d5fbabb9b20c41b))
* rewrite the README opening around what the app does ([#160](https://github.com/ruinosus/foundry-assured/issues/160)) ([73b9cc1](https://github.com/ruinosus/foundry-assured/commit/73b9cc17ce3b629939f55ceb2bd6d2c7070a0637))
* **wiki:** regenerate the wiki ([#153](https://github.com/ruinosus/foundry-assured/issues/153)) ([bec71a0](https://github.com/ruinosus/foundry-assured/commit/bec71a0c3db14aaee12205da27fea6603690e186))
* **wiki:** regenerate the wiki ([#158](https://github.com/ruinosus/foundry-assured/issues/158)) ([b1c0758](https://github.com/ruinosus/foundry-assured/commit/b1c0758914248fd8ea0eb6eaa1d6a2f2f352d1b4))
* **wiki:** regenerate the wiki ([#173](https://github.com/ruinosus/foundry-assured/issues/173)) ([398618a](https://github.com/ruinosus/foundry-assured/commit/398618a8062af384a6a92f72f1541ad23678eaae))

## [0.9.0](https://github.com/ruinosus/foundry-assured/compare/v0.8.0...v0.9.0) (2026-08-15)


### Features

* **infra:** declare the CI identity's data-plane roles in the Bicep ([#137](https://github.com/ruinosus/foundry-assured/issues/137)) ([a2d913f](https://github.com/ruinosus/foundry-assured/commit/a2d913ff43364c37988901a5072c0296c56c0370))
* **wiki:** add a rebuild input — "a wiki exists" is not "the right wiki exists" ([#147](https://github.com/ruinosus/foundry-assured/issues/147)) ([7e41ad6](https://github.com/ruinosus/foundry-assured/commit/7e41ad6f80befa024fae867b3fcdf763f8331a10))
* **wiki:** one wiki for the repository, not one per area ([#145](https://github.com/ruinosus/foundry-assured/issues/145)) ([49e00ab](https://github.com/ruinosus/foundry-assured/commit/49e00ab92f3fe509be80db6dd5ceaca6088d2d37))
* **wiki:** scope the generator to one area, and commit the citation contract ([#143](https://github.com/ruinosus/foundry-assured/issues/143)) ([4d10c9a](https://github.com/ruinosus/foundry-assured/commit/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa))
* **wiki:** the freshness check becomes a trigger, and the loop actually closes ([#139](https://github.com/ruinosus/foundry-assured/issues/139)) ([f8cd8c2](https://github.com/ruinosus/foundry-assured/commit/f8cd8c205c5ae09440eba9f3583f1238f65e47d6))


### Bug Fixes

* **wiki:** the fidelity gate graded the wrong bundle and reported success ([#141](https://github.com/ruinosus/foundry-assured/issues/141)) ([17007d0](https://github.com/ruinosus/foundry-assured/commit/17007d047c04d71b39fc69768e22595db86a1a8c))


### Documentation

* **adr:** ADR-016 — OpenWiki closes the freshness loop ADR-012 only opened ([#135](https://github.com/ruinosus/foundry-assured/issues/135)) ([f7dc471](https://github.com/ruinosus/foundry-assured/commit/f7dc4713525f052d594299d4dc7cf6d0ecaec3e4))
* **adr:** ADR-016 — survey the off-the-shelf tooling for the gates ([#148](https://github.com/ruinosus/foundry-assured/issues/148)) ([0dcf147](https://github.com/ruinosus/foundry-assured/commit/0dcf147bcc190ac69b370eeeac4865327f51df15))
* **wiki:** regenerate the backend wiki ([#144](https://github.com/ruinosus/foundry-assured/issues/144)) ([d2995d8](https://github.com/ruinosus/foundry-assured/commit/d2995d87bda06cd1515f3e5d246e9e3d77de9a30))

## [0.8.0](https://github.com/ruinosus/foundry-assured/compare/v0.7.1...v0.8.0) (2026-08-15)


### Features

* AgentSchema replaces the DNA SDK + deploy-validation fixes ([#130](https://github.com/ruinosus/foundry-assured/issues/130)) ([6d784e2](https://github.com/ruinosus/foundry-assured/commit/6d784e20559f26973f263726c6326bade18abe23))
* **backend:** compose agent prompts declaratively via DNA (ADR-013) ([#104](https://github.com/ruinosus/foundry-assured/issues/104)) ([5b0212b](https://github.com/ruinosus/foundry-assured/commit/5b0212b619f99932572fb8db9b384c7e8cab0a2a))
* **dna:** Decompose concierge prompts into Soul + Guardrails (post byte-lock) (s-decompose-prompts) ([#106](https://github.com/ruinosus/foundry-assured/issues/106)) ([ac26436](https://github.com/ruinosus/foundry-assured/commit/ac2643666a83940852f00f1c2ffcea48b1bbb653))
* **dna:** dna-sdk: git-dep → pacote oficial do PyPI (s-official-packages) ([#107](https://github.com/ruinosus/foundry-assured/issues/107)) ([ce22850](https://github.com/ruinosus/foundry-assured/commit/ce2285044adf54bc2346bdb70854883acd4307c5))
* **dna:** Prompts sem rebuild: volume mount do .dna no container (s-no-deploy-prompts) ([#108](https://github.com/ruinosus/foundry-assured/issues/108)) ([0aca940](https://github.com/ruinosus/foundry-assured/commit/0aca940a45134e658b7b6a0fcace48f8bd55bf7f))
* **dna:** Prompts sem redeploy em PRODUÇÃO: Azure Files mount no ACA (s-aca-azure-files-prompts) ([#110](https://github.com/ruinosus/foundry-assured/issues/110)) ([8a84b6c](https://github.com/ruinosus/foundry-assured/commit/8a84b6cb4e6dc14250f7ce0e402b6042cfe7bd0b))

## [0.7.1](https://github.com/ruinosus/foundry-assured/compare/v0.7.0...v0.7.1) (2026-07-02)


### Bug Fixes

* **deploy:** set APP_USERS_GROUP_ID in the deploy env (selfwiki ACL header) ([#92](https://github.com/ruinosus/foundry-assured/issues/92)) ([86d4b53](https://github.com/ruinosus/foundry-assured/commit/86d4b534472505daac9be252adbf919d36148425))

## [0.7.0](https://github.com/ruinosus/foundry-assured/compare/v0.6.0...v0.7.0) (2026-07-02)


### Features

* app RBAC + user management; rebrand to Foundry Assured; wiki-freshness gate; doc refresh ([#73](https://github.com/ruinosus/foundry-assured/issues/73)) ([d89dd2a](https://github.com/ruinosus/foundry-assured/commit/d89dd2ab932d6c54f5bf98c97289609c37b0ee23))
* **assurance:** Phase 5 — red-team gate (the ACL trim is injection-proof) ([#60](https://github.com/ruinosus/foundry-assured/issues/60)) ([6a29510](https://github.com/ruinosus/foundry-assured/commit/6a2951004c1a8ece4c9633d1ab971714f32c89ac))
* **assurance:** Phase 6 — package the mechanism (CI gates + METHOD + template) ([#62](https://github.com/ruinosus/foundry-assured/issues/62)) ([283fa6e](https://github.com/ruinosus/foundry-assured/commit/283fa6e52250d7afb21703738579f079286fe740))
* selfwiki deep-wiki domain + Assurance Console frontend ([#67](https://github.com/ruinosus/foundry-assured/issues/67)) ([1aec474](https://github.com/ruinosus/foundry-assured/commit/1aec474aecbce16a04602be7da38fe8c09e59d8f))


### Bug Fixes

* **assurance:** review fixes — attribution bug + robustness (wave 1: code/CI) ([#63](https://github.com/ruinosus/foundry-assured/issues/63)) ([4a4a78f](https://github.com/ruinosus/foundry-assured/commit/4a4a78f78714f99c25bbf6caac656f1adfceb16a))
* **wiki:** fidelity gate normalizes blob + external URLs (scores both generation paths) ([#74](https://github.com/ruinosus/foundry-assured/issues/74)) ([4e705ac](https://github.com/ruinosus/foundry-assured/commit/4e705ac67063bf19d0c8f4188ae23f38c0d65473))


### Documentation

* add identity & access setup map (what azd creates vs manual app regs) ([#70](https://github.com/ruinosus/foundry-assured/issues/70)) ([474772e](https://github.com/ruinosus/foundry-assured/commit/474772e9db48e6921d8c619752747e3353954292))
* adopt a documentation standard (Diátaxis + MS Learn) + Mermaid diagrams ([#65](https://github.com/ruinosus/foundry-assured/issues/65)) ([b1cfa58](https://github.com/ruinosus/foundry-assured/commit/b1cfa588a220b01426a26b6a874ba2ff6fc42f28))
* English consistency for markdown + add setup (azd-vs-manual) section to the deck ([#71](https://github.com/ruinosus/foundry-assured/issues/71)) ([d2bd49a](https://github.com/ruinosus/foundry-assured/commit/d2bd49a5c279b274ea0063dcdf6a5f45ef102fef))
* fix fidelity range + add flow & comparison pages with back-nav ([#68](https://github.com/ruinosus/foundry-assured/issues/68)) ([4cd8a40](https://github.com/ruinosus/foundry-assured/commit/4cd8a40f2ddafc6709c388bbc11b573e52eb4b05))
* fix Pages URLs after repo rename to foundry-assured ([#69](https://github.com/ruinosus/foundry-assured/issues/69)) ([7af8eeb](https://github.com/ruinosus/foundry-assured/commit/7af8eebf6a3d4875b32eaf6d55f456a423b009f9))
* RBAC + user-management plan (Entra App Roles, via the portal) ([#72](https://github.com/ruinosus/foundry-assured/issues/72)) ([ddb15fa](https://github.com/ruinosus/foundry-assured/commit/ddb15fa079917c0f2619e313f760dc727bf4c0f9))
* review fixes — align all docs with the as-built model (wave 2) ([#64](https://github.com/ruinosus/foundry-assured/issues/64)) ([0e6c461](https://github.com/ruinosus/foundry-assured/commit/0e6c4618a2fd63b148519045476c30866bae9ddd))

## [Unreleased]

The **multi-tenant SaaS evolution** (sub-projects A→B→C→D) built on top of the shipped
v0.6.0 showcase + assurance mechanism. One codebase, three deployment modes
(`self_hosted` / `dedicated` / `shared`); decisions captured in **ADRs 001–011**
(`docs/adr/`), target architecture in
`docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md`.

### Features

* **saas/A:** multi-tenant foundation — `TenantConfigProvider` seam (Single/Multi) behind a `DEPLOYMENT_MODE` switch, per-request tenant resolution from the Entra `tid` + OBO downstream, memory namespaced by tenant, swappable tenant store (Azure Table / in-memory) (ADR-003, ADR-006, ADR-007)
* **saas/B:** per-tenant connections — `TenantRecord` + `Connection` records that **reference** Foundry connections (never store a secret), an Admin `/tenant` API + a Connections admin page (ADR-005, ADR-008)
* **saas/C:** credential brokering + write governance — the **platform** agent's MCP tools driven by the tenant's Connection records; credentials resolved Microsoft-natively (OBO for Microsoft-audience servers, Foundry connections otherwise — never reads a secret); per-tool RBAC (stricter-of-both); WRITE tools gated by the framework's native tool-approval (Approver/Admin) (ADR-009)
* **saas/D-runtime:** shared-mode enablement — domains mount globally and are gated per-tenant by **DomainAssignment** (a per-tenant license entitlement, `enabled_domains`), seeded at onboarding and managed via `/tenant/domains`; the `/platform-hosted` twin endpoint (ADR-010)
* **saas/D-packaging:** the deployable **platform hosted agent** (Invocations protocol + Foundry Toolbox + OAuth identity passthrough); the **dedicated stamp** as an Azure **Managed Application** (`infra/managed-app/`) + Azure **Lighthouse** (`infra/lighthouse/`); a tier→domains entitlement map (ADR-002, ADR-011)
* **domains:** add a fourth, **tool-driven** domain — `platform`, an ops concierge over Microsoft first-party MCP servers (Learn, Azure, Entra, Azure DevOps, GitHub) with HITL approval on write actions and a live-vs-hosted toggle

### Documentation

* SaaS target architecture design + ADRs 001–011 (`docs/adr/`), sub-project specs/plans (`docs/superpowers/`), the `docs/D-PACKAGING-RUNBOOK.md` packaging runbook, `docs/COST.md`, and `docs/BRANCHING.md` (Git Flow)

## [0.6.0](https://github.com/ruinosus/foundry-helpdesk/compare/v0.5.0...v0.6.0) (2026-06-27)


### Features

* **assurance:** Phase 4 — access-control gate (query-time ACL trimming) ([#56](https://github.com/ruinosus/foundry-helpdesk/issues/56)) ([3cfe4e5](https://github.com/ruinosus/foundry-helpdesk/commit/3cfe4e587af14c70fdefd25b9939ad1a7695ebd9))


### Refactors

* **assurance:** classification is owner data, not code ([#59](https://github.com/ruinosus/foundry-helpdesk/issues/59)) ([585dc57](https://github.com/ruinosus/foundry-helpdesk/commit/585dc57c0eb1bc2577aa64808706eb572af602f8))

## [0.5.0](https://github.com/ruinosus/foundry-helpdesk/compare/v0.4.1...v0.5.0) (2026-06-27)


### Features

* **assurance:** Phase 0 thresholds + Phase 2 retrieval recall tuning ([#51](https://github.com/ruinosus/foundry-helpdesk/issues/51)) ([af97778](https://github.com/ruinosus/foundry-helpdesk/commit/af97778e078f89c5174ef719dae8f242b1d51401))
* **assurance:** Phase 1 — deterministic fidelity gate on wiki build ([#54](https://github.com/ruinosus/foundry-helpdesk/issues/54)) ([61ca083](https://github.com/ruinosus/foundry-helpdesk/commit/61ca083c9f32abbc4d291d17d7d2f61d3cb27a38))
* **assurance:** Phase 3 — deterministic completeness gate ([#53](https://github.com/ruinosus/foundry-helpdesk/issues/53)) ([66c4e58](https://github.com/ruinosus/foundry-helpdesk/commit/66c4e580d1fa0a73828e8fa3d79938bb5a4155f7))
* **assurance:** Phase 4 infra — Entra ACL groups (Bicep) + test users ([#55](https://github.com/ruinosus/foundry-helpdesk/issues/55)) ([82dd4f8](https://github.com/ruinosus/foundry-helpdesk/commit/82dd4f8df09f5ba179ff8285484b4d9d32d6f027))


### Documentation

* KB→agent assurance mechanism — full implementation plan ([#50](https://github.com/ruinosus/foundry-helpdesk/issues/50)) ([4d069bb](https://github.com/ruinosus/foundry-helpdesk/commit/4d069bba4f364a470bb1bcbb08716aff0f4c57d8))

## [0.4.1](https://github.com/ruinosus/foundry-helpdesk/compare/v0.4.0...v0.4.1) (2026-06-27)


### Bug Fixes

* **cockpit:** retrieval starved by over-broad tool-message filter ([#49](https://github.com/ruinosus/foundry-helpdesk/issues/49)) ([d6aad55](https://github.com/ruinosus/foundry-helpdesk/commit/d6aad554041e3892ad39b1a455243dfbcf429ff3))
* **cockpit:** semantic retrieval so multi-turn chat works ([#47](https://github.com/ruinosus/foundry-helpdesk/issues/47)) ([3a6bb34](https://github.com/ruinosus/foundry-helpdesk/commit/3a6bb34fe220a979d578f823d5ff8a74a231129e))

## [0.4.0](https://github.com/ruinosus/foundry-helpdesk/compare/v0.3.0...v0.4.0) (2026-06-27)


### Features

* **ci:** use a GitHub App token for release-please (enterprise/compliant) ([#45](https://github.com/ruinosus/foundry-helpdesk/issues/45)) ([9a94348](https://github.com/ruinosus/foundry-helpdesk/commit/9a9434810e2b3fec9c84ce9f9918fc11cbcb3ac0))


### Bug Fixes

* **ci:** cut the release when release-please leaves it untagged ([#42](https://github.com/ruinosus/foundry-helpdesk/issues/42)) ([4e09190](https://github.com/ruinosus/foundry-helpdesk/commit/4e09190ed86063a9a232cef8521380cce81d9bdc))
* **deploy:** set COCKPIT_AGUI_URL on the web container ([#44](https://github.com/ruinosus/foundry-helpdesk/issues/44)) ([866eca0](https://github.com/ruinosus/foundry-helpdesk/commit/866eca0df5eb44725f07d80e875d0a84e5ccef30))

## [0.3.0](https://github.com/ruinosus/foundry-helpdesk/compare/v0.2.0...v0.3.0) (2026-06-26)


### Features

* **ci:** evaluate the deployed agent with the official Foundry ai-agent-evals action ([#31](https://github.com/ruinosus/foundry-helpdesk/issues/31)) ([180d188](https://github.com/ruinosus/foundry-helpdesk/commit/180d18844155afdf3a6f0ffbf4aaa29695a6160f))
* **cockpit:** Cockpit expert agent + grounded-qa Skill (deep-wiki, SKILL.md) ([#34](https://github.com/ruinosus/foundry-helpdesk/issues/34)) ([bcae908](https://github.com/ruinosus/foundry-helpdesk/commit/bcae908a796764f297faf593ecb5fb849e317a33))
* **cockpit:** deploy the Cockpit expert as a hosted Foundry agent (Phase C) ([#39](https://github.com/ruinosus/foundry-helpdesk/issues/39)) ([4a48cdc](https://github.com/ruinosus/foundry-helpdesk/commit/4a48cdcff8e21f35aa981e1e8d5fe90f5f59675b))
* **cockpit:** ingest the Cockpit docbundles into a second Foundry IQ KB ([#33](https://github.com/ruinosus/foundry-helpdesk/issues/33)) ([b7a1fce](https://github.com/ruinosus/foundry-helpdesk/commit/b7a1fce5860115d0be06a303f5393659fb276429))
* **dx:** MarkItDown converter for non-markdown corpora ([#32](https://github.com/ruinosus/foundry-helpdesk/issues/32)) ([d91c5d3](https://github.com/ruinosus/foundry-helpdesk/commit/d91c5d3b0cc13d519ea17d1fa91153b29c55944b))
* **evals:** render real eval scores live from Foundry (not a local mirror) ([#29](https://github.com/ruinosus/foundry-helpdesk/issues/29)) ([0eefe9b](https://github.com/ruinosus/foundry-helpdesk/commit/0eefe9b35f72674e52e1927010b5877c136418a8))
* **eval:** wire the Cockpit golden into the eval harness (--domain cockpit) ([#41](https://github.com/ruinosus/foundry-helpdesk/issues/41)) ([6779a21](https://github.com/ruinosus/foundry-helpdesk/commit/6779a21c4829f6ee6c38488f243ef45e7af10e4d))
* **wiki:** instrument Wiki Builder cost + wire Foundry observability ([#37](https://github.com/ruinosus/foundry-helpdesk/issues/37)) ([4acf379](https://github.com/ruinosus/foundry-helpdesk/commit/4acf37944089e08d7a2fef6710cf234a8095a891))
* **wiki:** Wiki Builder — generate a faithful LLM wiki from source on Foundry ([#35](https://github.com/ruinosus/foundry-helpdesk/issues/35)) ([66db7d3](https://github.com/ruinosus/foundry-helpdesk/commit/66db7d3e5c8f1805c42326e30a78c3a53bfb3c21))


### Bug Fixes

* **cockpit:** re-index fresh + reconcile deletions on ingest ([#40](https://github.com/ruinosus/foundry-helpdesk/issues/40)) ([87a0236](https://github.com/ruinosus/foundry-helpdesk/commit/87a0236de04f3bdab2fb76e16ba35c3523a7f222))
* **frontend:** serve CopilotKit v2 agent-run paths via catch-all route ([#38](https://github.com/ruinosus/foundry-helpdesk/issues/38)) ([5b5c37e](https://github.com/ruinosus/foundry-helpdesk/commit/5b5c37ed6089982f9922e56bd23d965a7cb02189))


### Documentation

* case study — the source-grounded LLM wiki loop (measured) ([#36](https://github.com/ruinosus/foundry-helpdesk/issues/36)) ([4c76fdf](https://github.com/ruinosus/foundry-helpdesk/commit/4c76fdf93bee86632080ce26369e13259219dc08))

## [0.2.0](https://github.com/ruinosus/foundry-helpdesk/compare/v0.1.0...v0.2.0) (2026-06-26)


### Features

* **demo:** no-Azure demo mode via CopilotKit aimock (AG-UI replay) ([#26](https://github.com/ruinosus/foundry-helpdesk/issues/26)) ([1d4bb21](https://github.com/ruinosus/foundry-helpdesk/commit/1d4bb21573a4592d23e4408ec99ff34d080c851b))
* **demo:** record real AG-UI fixtures + fix replay via aimock --config ([#28](https://github.com/ruinosus/foundry-helpdesk/issues/28)) ([ffdc1f4](https://github.com/ruinosus/foundry-helpdesk/commit/ffdc1f4d2cc3dc7fb5e4a0b10c98f5f56061b50e))
* **dx:** one-command bootstrap + Entra setup scripts ([#24](https://github.com/ruinosus/foundry-helpdesk/issues/24)) ([32c75ab](https://github.com/ruinosus/foundry-helpdesk/commit/32c75ab7f708efc7a041f041c5b97c4138247294))
* persist tickets (Azure Files), point evals at Foundry, gate read APIs ([#22](https://github.com/ruinosus/foundry-helpdesk/issues/22)) ([56bf2b8](https://github.com/ruinosus/foundry-helpdesk/commit/56bf2b8acc9ea5ab3347b1c5685f3af3b1862028))


### Bug Fixes

* **deploy:** Entra OBO secret wiring + frontend public/ + cost docs ([#17](https://github.com/ruinosus/foundry-helpdesk/issues/17)) ([801b8a6](https://github.com/ruinosus/foundry-helpdesk/commit/801b8a6de94a3bf2e94b0b6e39db5c37e6b50177))
* **deps:** unblock Dependabot — pin python 3.12, ignore framework-driven deps ([#12](https://github.com/ruinosus/foundry-helpdesk/issues/12)) ([bfdf479](https://github.com/ruinosus/foundry-helpdesk/commit/bfdf4791876e02b67741c0ad2619a44d8bed455f))
* import useAgent from /v2 (shared context) not /v2/headless ([4202fe1](https://github.com/ruinosus/foundry-helpdesk/commit/4202fe16e80f8789e2320477d70c0d1505695a2b))
* memory store ops are under client.beta.memory_stores (not .memory_stores) ([a70a3c5](https://github.com/ruinosus/foundry-helpdesk/commit/a70a3c5e608b6b05f74706aa4b23c07d22bdc8f8))
* **security:** enforce Entra auth in production + dev-only inspector ([#18](https://github.com/ruinosus/foundry-helpdesk/issues/18)) ([6379d8f](https://github.com/ruinosus/foundry-helpdesk/commit/6379d8f854aa0b46b05f0bc1a9696284f0bedbb4))
* useInterrupt agentId=helpdesk (defaulted to 'default') ([d48120c](https://github.com/ruinosus/foundry-helpdesk/commit/d48120cb976c88ecd160bc4c4f2c9ec50c44b88c))


### Documentation

* add "Make it yours" extension recipe + centralize UI branding ([#23](https://github.com/ruinosus/foundry-helpdesk/issues/23)) ([ed37f01](https://github.com/ruinosus/foundry-helpdesk/commit/ed37f014d9e0f2608dd975d76ed1e3df49fb5e6e))
* **cost:** add Azure Files (tickets persistence) line to the cost table ([#25](https://github.com/ruinosus/foundry-helpdesk/issues/25)) ([d4e2b32](https://github.com/ruinosus/foundry-helpdesk/commit/d4e2b32fef952b26c701d4e8ca74b9a2b5d52fc1))
* **customize:** document swapping the eval datasets (5th swap point) ([#27](https://github.com/ruinosus/foundry-helpdesk/issues/27)) ([4f318c9](https://github.com/ruinosus/foundry-helpdesk/commit/4f318c90402dab4abfe302a3e58c7efe381b1ab8))
