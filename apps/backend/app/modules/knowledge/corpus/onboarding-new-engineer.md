# Runbook: Onboarding a new engineer

**Applies to:** First-day setup for engineers joining a product team.

## Day 1 checklist
1. Activate corp identity (SSO) and enroll in MFA.
2. Join the team's GitHub org; default access is **read** on all repos, **write** on the team's repos.
3. Install the toolchain: `git`, `uv` (Python), Node 22 LTS, Docker, and the corp VPN client.
4. Clone the team monorepo and run `make bootstrap`.
5. Request access to the staging environment (production access is granted later — see the prod access runbook).

## Accounts provisioned automatically
- Email, Slack, GitHub, Jira, and the observability dashboards.

## Accounts requested manually
- Production database read replicas, cloud console, and PagerDuty (after on-call shadowing).

## Buddy
Each new engineer is paired with an onboarding buddy for the first two weeks. The buddy approves the first pull request and walks through the deploy pipeline.
