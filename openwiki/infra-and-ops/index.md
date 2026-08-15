# Files

- [azd service graph and deployment hooks](azd-and-hooks.md) - How azure.yaml composes backend, web, and hosted-agent services, and how postprovision/postdeploy hooks reconcile build-time auth config and deploy-time identities.
- [Infrastructure topology](infra.md) - Bicep-defined Azure topology for Foundry, Search, storage, Container Apps, and the dedicated-stamp extension seams. Use this page to trace deployment outputs back to runtime behavior.
- [Operational scripts and end-to-end flows](scripts-and-e2e.md) - Repository scripts for bootstrap, auth setup, prompt publishing, and one-shot deployment, plus Playwright browser tests that verify auth, ACL, and runtime behavior.
