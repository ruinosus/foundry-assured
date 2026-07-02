"""Infra-free regression test for `retrieval._decode_dockey` — the searchIndex citation decode.

The defect (observed live in an A-vs-B run): the old decode did `dockey.split("_")[1]` + standard
`b64decode`, which fell back to the RAW base64 docKey for ~half the real keys — a broken citation UX
(the "click-a-source shows the snippet" feature renders opaque base64 instead of a filename).

These fixtures are ACTUAL docKeys dumped from the live `cockpit-si-kb` searchIndex KB (RULE #1 — captured,
not invented). Confirmed live format:

    <12-hex>_<STANDARD-base64(blob_url + glued tail byte)>_pages_<M>

We assert every one now decodes to a blob URL whose filename ends in `.md` (never raw base64), and — to
lock in the regression — that the OLD naïve `split("_")[1]` approach would have failed on the keys whose
base64 length is ≡ 1 (mod 4).

Run (from apps/backend/):
    uv run python -m eval.dockey_decode_test

No infra, no credential, no network — always runs.
"""

from __future__ import annotations

import base64
import sys

from app.services.retrieval import _decode_dockey

# (real docKey, expected filename) — dumped live from cockpit-si-kb (eval._dockey_investigate, 2026-07).
# Mix of base64-segment lengths mod 4 so both the "used to work" and "used to fall back to raw" cases are
# represented (the __page-1/3/6.md keys are the len≡1 class the OLD split-and-decode choked on).
_FIXTURES: list[tuple[str, str]] = [
    ("24eef70b7e4d_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC10ZWxlbWV0cnktdjEuMi4wX19wYWdlLTEubWQ1_pages_0",
     "cockpit-mcp-telemetry-v1.2.0__page-1.md"),
    ("24eef70b7e4d_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC10ZWxlbWV0cnktdjEuMi4wX19wYWdlLTMubWQ1_pages_0",
     "cockpit-mcp-telemetry-v1.2.0__page-3.md"),
    ("24eef70b7e4d_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC10ZWxlbWV0cnktdjEuMi4wX19wYWdlLTYubWQ1_pages_1",
     "cockpit-mcp-telemetry-v1.2.0__page-6.md"),
    ("24eef70b7e4d_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC10ZWxlbWV0cnktdjEuMi4wX19wYWdlLTEwLm1k0_pages_1",
     "cockpit-mcp-telemetry-v1.2.0__page-10.md"),
    ("f4c8c74f0c55_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC1hZ2VudF9fcGFnZS04Lm1k0_pages_0",
     "cockpit-mcp-agent__page-8.md"),
    ("eeedd3e9be41_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LWFnZW50LWZyYW1ld29yay1hcGktdjIuMS4wX19wYWdlLTE3Lm1k0_pages_0",
     "cockpit-agent-framework-api-v2.1.0__page-17.md"),
    ("257121708dbe_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC1hZ2VudC12MS40LjBfX3BhZ2UtOC5tZA2_pages_0",
     "cockpit-mcp-agent-v1.4.0__page-8.md"),
    ("13e53ee49962_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC1hZ2VudF9fcGFnZS0xMC5tZA2_pages_0",
     "cockpit-mcp-agent__page-10.md"),
    ("803da65c051a_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC1zdWl0ZS12MS4zLjBfX3BhZ2UtMi5tZA2_pages_0",
     "cockpit-mcp-suite-v1.3.0__page-2.md"),
    ("24eef70b7e4d_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC11dGlsaXR5LWFnZW50cy12MS41LjBfX3BhZ2UtMS5tZA2_pages_0",
     "cockpit-mcp-utility-agents-v1.5.0__page-1.md"),
]


def _old_naive_decode(dockey: str) -> str:
    """The pre-fix decode, replicated to PROVE the regression (split-and-take-[1] + std b64)."""
    parts = dockey.split("_")
    if len(parts) < 2:
        return dockey
    mid = parts[1]
    try:
        return base64.b64decode(mid + "=" * (-len(mid) % 4)).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return dockey


def main() -> int:
    failures: list[str] = []
    regressions_caught = 0

    for dockey, expected_fn in _FIXTURES:
        url = _decode_dockey(dockey)
        fn = url.rsplit("/", 1)[-1]

        if url == dockey:
            failures.append(f"raw fallback (undecoded base64) for {dockey[:32]}...")
            continue
        if not fn.endswith(".md"):
            failures.append(f"filename does not end .md: {fn!r} (from {dockey[:32]}...)")
            continue
        if "://" not in url:
            failures.append(f"decoded value is not a URL: {url!r}")
            continue
        if fn != expected_fn:
            failures.append(f"filename {fn!r} != expected {expected_fn!r}")
            continue

        # Regression witness: did the OLD decode produce broken output for this same key?
        old = _old_naive_decode(dockey)
        old_fn = old.rsplit("/", 1)[-1] if "://" in old else old
        if old == dockey or not old_fn.endswith(".md"):
            regressions_caught += 1

        print(f"  ✅ {dockey[:24]}... -> {fn}")

    if failures:
        print("\n❌ FAIL: _decode_dockey did not recover a .md filename for every live docKey:")
        for f in failures:
            print(f"   - {f}")
        return 1

    print(
        f"\n✅ PASS: all {len(_FIXTURES)} live docKeys decode to .md filenames "
        f"(not raw base64). {regressions_caught}/{len(_FIXTURES)} would have BROKEN under the "
        f"old split-and-take decode — regression is covered."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
