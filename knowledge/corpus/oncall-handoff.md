# Runbook: On-call handoff

**Applies to:** Engineers rotating on and off the primary on-call shift.

## Cadence
Shifts run one week, handed off every Monday at 10:00 local time in the on-call channel.

## Outgoing engineer provides
1. Open incidents and their current state.
2. Anything "watch this" — a flaky alert, a deploy in progress, a degraded dependency.
3. Silenced alerts and why (with expiry).
4. Links to any in-flight postmortems.

## Incoming engineer confirms
1. PagerDuty shows them as primary.
2. They can receive a test page.
3. They have prod read access and the incident runbooks bookmarked.

## Escalation path
Primary → secondary (15 min no-ack) → engineering manager → incident commander on rotation. If you can't reach the secondary during a SEV1, page the manager directly.
