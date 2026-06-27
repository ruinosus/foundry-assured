# Changelog

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
