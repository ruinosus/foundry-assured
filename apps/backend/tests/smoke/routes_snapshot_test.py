"""Route-surface snapshot — the refactor's safety net (Phase 0).

The modular-monolith refactor claims "no behavior change" while moving nearly every file.
A forgotten import, a router that stops being included, or a conditional gate that flips
would all still let the process boot. This pins the HTTP surface instead: method + path for
every route, under two fixed deployment profiles.

Two profiles, because the surface is conditional: `shared` mounts the `/tenant` router that
`self_hosted` does not (ADR-010's entitlement side is a dependency, not a route, so it does
not show up here — that is what `eval/domain_gate_test.py` covers).

Each profile is captured in its own subprocess (see `_capture_routes`): `settings` and the
registry are read at import time, so two profiles in one interpreter would measure the first
one's leftovers.

    uv run python -m tests.smoke.routes_snapshot_test            # verify
    uv run python -m tests.smoke.routes_snapshot_test --update   # re-record (review the diff!)
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import app as _app

BACKEND = pathlib.Path(_app.__file__).resolve().parent.parent
FIXTURE = pathlib.Path(__file__).with_name("routes_snapshot.json")
PROFILES = ("self_hosted", "self_hosted_oncall", "shared")


def capture(profile: str) -> list[list[str]]:
    """Build the app under `profile` in a clean interpreter and return its routes."""
    result = subprocess.run(
        [sys.executable, "-m", "tests.smoke._capture_routes", profile],
        capture_output=True,
        text=True,
        cwd=BACKEND,
        check=False,  # the returncode is reported below with the captured stderr
    )
    if result.returncode != 0:
        raise RuntimeError(f"capture failed for {profile}:\n{result.stderr[-2000:]}")
    return json.loads(result.stdout)


def main() -> int:
    current = {profile: capture(profile) for profile in PROFILES}

    if "--update" in sys.argv:
        FIXTURE.write_text(json.dumps(current, indent=2) + "\n")
        for profile in PROFILES:
            print(f"  recorded {profile}: {len(current[profile])} routes")
        print(f"\n✅ snapshot written to {FIXTURE.name} — review the diff before committing.")
        return 0

    if not FIXTURE.exists():
        print(f"❌ {FIXTURE.name} missing. Record it with --update.")
        return 1

    baseline = json.loads(FIXTURE.read_text())
    failures: list[str] = []

    for profile in PROFILES:
        want = {tuple(r) for r in baseline.get(profile, [])}
        got = {tuple(r) for r in current[profile]}
        if want == got:
            print(f"  ✓ {profile}: {len(got)} routes unchanged")
            continue
        failures.append(profile)
        print(f"  ✗ {profile}: route surface changed")
        for method, path in sorted(want - got):
            print(f"      LOST  {method:7s} {path}")
        for method, path in sorted(got - want):
            print(f"      NEW   {method:7s} {path}")

    if failures:
        print(
            f"\n❌ route surface changed in: {', '.join(failures)}.\n"
            "   If the change is intended, re-record with --update and say so in the PR."
        )
        return 1
    print("\n✅ route surface identical to the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
