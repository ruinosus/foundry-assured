# Runbook: Responding to cloud cost alerts

**Applies to:** Teams that own a cloud cost budget.

## Trigger
You received a budget alert that your team's monthly spend is forecast to exceed the budget by >20%.

## Investigate
1. Open the cost dashboard filtered to your team tag.
2. Sort by the largest week-over-week increase.
3. Common culprits: an orphaned GPU instance, a runaway batch job, untiered storage growth, or a forgotten staging environment left running.

## Act
- Stop or right-size the offending resource.
- For storage, apply lifecycle rules to tier cold data.
- For compute left running, prefer scheduled auto-shutdown over manual stop.

## Important
Don't delete a resource you didn't create without confirming ownership in the team channel — it may be load-bearing. Tag the owner and agree before removing.
