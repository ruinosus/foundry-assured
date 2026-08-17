---
type: operations
title: Scripts and Runbooks
description: "Operational scripts that provision, bootstrap, and maintain the repository’s environments, including what they automate, what they assume, and what intentionally remains manual."
tags: [operations, scripts, runbooks]
---

# Scripts and runbooks

The `scripts/` directory is the operational glue between infrastructure, backend knowledge setup, Entra app registration, and local developer workflows.

## `up-all.sh` orchestration

`up-all.sh` is the main one-shot orchestrator. Its header documents the exact staged flow:

1. preflight for `azd`, `az`, `uv`, and `node`
2. optional Entra app registration and app-role setup
3. `azd up`, with hook-driven env push/RBAC/redirect automation
4. explicit data-plane bootstrap via `bootstrap.sh`

[Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L1-L16) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L49-L66) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L68-L87) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L100-L110)

The script is explicit that some tasks remain manual: consent, extra KB ingests, toolbox binding, and managed application publishing. That boundary matters when debugging “fully automated” deployment assumptions. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L125-L132)

## Entra and role setup

`setup-entra.sh`, `setup-app-roles.sh`, and `assign-admin-role.sh` support auth-enabled deployments. `up-all.sh --with-auth` chains them before provisioning because the web build bakes `NEXT_PUBLIC_*` values at build time. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L68-L80) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L89-L103)

## Bootstrap and postdeploy hooks

The deployment contract is split intentionally:

- `bootstrap.sh` handles slower, data-plane-fragile work like KB ingest and memory provisioning in the open.
- hook scripts handle environment propagation and postdeploy RBAC/redirect tasks.

This split is meant to keep long-running or failure-prone data-plane steps visible rather than hidden in azd hooks. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L105-L110)

## Other operational scripts

Not every script is part of the main happy path, but several are important extension seams:

- `push-prompts.sh` — prompt distribution
- `sync-gh-variables.sh` — GitHub deployment/config sync
- `demo.sh` and `demo-record.sh` — frontend fixture demo mode lifecycle
- `to-markdown.sh` — document conversion utility

These should be changed only when the operational workflow they support actually changes.
