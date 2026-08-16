# Reference: Incident severity levels

**Applies to:** Production incident classification and response.

## Levels
- **SEV1 — Critical:** customer-facing outage or data loss. Page on-call immediately, open an incident bridge, notify leadership within 15 minutes.
- **SEV2 — Major:** significant degradation, key feature broken, no full outage. Page on-call, update status page.
- **SEV3 — Minor:** limited impact, workaround exists. Handle during business hours.
- **SEV4 — Low:** cosmetic or internal-only. Track as a normal ticket.

## Who declares
Any engineer can declare a SEV1 or SEV2. When in doubt, declare higher — it's cheaper to downgrade than to under-respond.

## Required for SEV1/SEV2
An incident commander, a scribe, and a dedicated channel. A postmortem is mandatory within 5 business days and must be blameless.
