# Changelog

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
