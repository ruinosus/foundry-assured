# Runbook: Kubernetes pod in CrashLoopBackOff

**Applies to:** Services running on the shared AKS clusters.

## Triage
1. `kubectl get pods -n <ns>` — confirm the `CrashLoopBackOff` status and restart count.
2. `kubectl logs <pod> -n <ns> --previous` — read the logs from the crashed container, not the restarting one.
3. `kubectl describe pod <pod> -n <ns>` — check Events for OOMKilled, failed mounts, or image pull errors.

## Common causes
- **OOMKilled:** the container exceeded its memory limit. Raise `resources.limits.memory` or fix the leak.
- **Failed readiness probe:** the app starts slower than the probe allows. Increase `initialDelaySeconds`.
- **Missing secret/config:** a referenced Secret or ConfigMap doesn't exist in the namespace.

## Escalation
If the crash is in a platform sidecar (service mesh, logging agent) rather than your container, escalate to the **Platform** team with the pod name and namespace.
