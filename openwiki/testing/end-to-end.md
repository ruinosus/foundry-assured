---
type: testing
title: End-to-End Tests
description: "Playwright and browser-level validation flows that prove authentication, domain rendering, hosted/live chat paths, and structured citation behavior across the deployed stack."
tags: [testing, e2e, playwright]
---

# End-to-end tests

The `e2e/` suite is the browser-level proof that frontend routing, auth, backend chat surfaces, and hosted/live paths work together.

## Smoke flow

`e2e/smoke.spec.ts` is the main scenario. It signs in once, preserves MSAL session state in one browser context, visits each domain route, submits a helpdesk prompt, probes hosted mode on selfwiki, and checks structured citations on techdocs. The file header and comments are unusually descriptive about what each step proves. It also encodes current mismatches worth knowing: the test still visits techdocs even though the frontend registry can hide that domain, and it probes hosted behavior on selfwiki because that path is a useful integration canary even when frontend domain visibility or backend provisioning is environment-dependent. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/e2e/smoke.spec.ts#L6-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/e2e/smoke.spec.ts#L72-L80) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/e2e/smoke.spec.ts#L123-L132) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/e2e/smoke.spec.ts#L170-L185) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/e2e/smoke.spec.ts#L190-L209)

## Auth and MFA

The smoke test drives an Entra login redirect and delegates MFA setup/challenge handling to `entra-mfa.ts`. This is why the E2E suite can prove real auth behavior instead of only cookie stubbing. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/e2e/smoke.spec.ts#L30-L57)

## Diagnostics philosophy

The smoke suite records console warnings/errors, failed requests, interesting responses, and AG-UI run streams to artifacts so a browser failure can be debugged without immediately reproducing it in backend logs. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/e2e/smoke.spec.ts#L77-L118)

## What the suite is best at

E2E tests are the fastest way to catch:

- expired or missing token refresh behavior
- broken domain mounts
- proxy route/auth forwarding issues
- hosted/live UI toggle regressions
- evidence/citation rendering regressions

They are slower and more environment-dependent than backend tests, so use them after the narrower backend/module checks have passed.
