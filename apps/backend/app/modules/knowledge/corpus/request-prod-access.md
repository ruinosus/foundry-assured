# Runbook: Requesting production access

**Applies to:** Engineers who need read or write access to production systems.

## Access tiers
- **Prod read:** logs, metrics, read replicas. Granted after 30 days and one completed on-call shadow.
- **Prod write:** deploy + database write. Requires manager approval and a completed security training.
- **Break-glass:** emergency full access during an incident. Time-boxed to 4 hours, fully audited.

## How to request
1. Open an access request in the IT portal, selecting the tier and the specific system.
2. Tag your manager as approver. Prod write also requires the system owner's approval.
3. Access is provisioned via just-in-time (JIT) elevation — it expires automatically after the granted window.

## Important
Standing production write access is not granted. All prod write is JIT and time-boxed. Sharing elevated sessions or credentials is prohibited.
