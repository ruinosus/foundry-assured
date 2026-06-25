# Runbook: Dealing with flaky CI tests

**Applies to:** The shared CI pipeline (GitHub Actions) for backend services.

## Identify
A test is "flaky" if it passes and fails on the same commit without code changes. The CI dashboard tags reruns with a `retry` marker; three or more retries in a week flags the test.

## Immediate mitigation
1. Re-run the failed job once. If it passes, capture the run URL.
2. If a known-flaky test blocks an urgent merge, quarantine it with the `@pytest.mark.flaky` marker and open a tracking ticket. Quarantine is temporary — the owning team must fix or delete within two weeks.

## Root-cause checklist
- Shared mutable state between tests (fix: isolate fixtures).
- Time/order dependence (fix: freeze time, sort inputs).
- Real network calls (fix: mock the boundary).

## Policy
Never disable a test permanently to make CI green. Quarantine with a ticket, or fix it. A muted test with no tracking ticket is a process violation.
