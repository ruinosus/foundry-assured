# Runbook: Deploy rollback procedure

**Applies to:** Services deployed through the standard GitOps pipeline.

## When to roll back
Roll back if a deploy causes elevated error rates, latency spikes, or failed health checks that don't recover within 5 minutes.

## Procedure
1. Identify the last known-good release tag from the deploy history: `argocd app history <app>`.
2. Roll back: `argocd app rollback <app> <revision>`.
3. Confirm the rolled-back revision is `Synced` and `Healthy`.
4. Verify error rate and latency return to baseline on the service dashboard.
5. Post in the incident channel with the bad revision, the restored revision, and a one-line cause.

## After rollback
Open a ticket to fix forward. Do not re-deploy the bad revision until the root cause is fixed and a regression test is added. A rollback is mitigation, not a fix.
