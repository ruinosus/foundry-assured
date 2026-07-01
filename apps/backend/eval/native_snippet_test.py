"""Infra-free regression test for the NATIVE-path per-citation snippet (content-on-click).

Locks in the fix for the "sem prévia" regression: the native retrieve's per-citation `snippet` is read
from `references[].sourceData.snippet` (populated by `includeReferenceSourceData=true` on the ksp), NOT
from the old `references[].id` ↔ `response`-chunk `ref_id` join — which never fired on the `answerSynthesis`
KB (there `response` is the prose answer, not a JSON chunk array, so every snippet came back empty).

The fixture below is a REAL native-retrieve response dumped LIVE from `cockpit-si-kb` (eval/_dump_native,
now removed) with the snippets truncated for size. No Azure, no credential, no network — this is a pure
`_parse_native` contract test.

Run (from apps/backend/):
    uv run python -m eval.native_snippet_test

Always runs (no infra). Exit 0 ✅ every citation carries non-empty snippet · 1 a citation lost its snippet.
"""

from __future__ import annotations

import sys

from app.services import retrieval

# REAL native-retrieve response (cockpit-si-kb, includeReferenceSourceData=true, User A, live-dumped;
# snippets truncated). sourceData carries {uid, blob_url, snippet}; response is the answerSynthesis prose.
_LIVE_BODY = {
    "references": [
        {
            "type": "searchIndex",
            "id": "0",
            "activitySource": 1,
            "sourceData": {
                "uid": "24eef70b7e4d_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC10ZWxlbWV0cnktdjEuMi4wX19wYWdlLTEubWQ1_pages_0",
                "blob_url": "https://stassureds3vvlng2zilqy.blob.core.windows.net/cockpit-corpus/cockpit-mcp-telemetry-v1.2.0__page-1.md",
                "snippet": "# cockpit-mcp-telemetry v1.2.0 — Visão Geral do Repositório\n\n## Visão Geral do Repositório\n\nO `cockpit-mcp-telemetry` é um **servidor MCP (Model Context Protocol)** escrito em **.NET 8 (C#)**.",
            },
            "rerankerScore": 3.9875576,
            "docKey": "24eef70b7e4d_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LW1jcC10ZWxlbWV0cnktdjEuMi4wX19wYWdlLTEubWQ1_pages_0",
        },
        {
            "type": "searchIndex",
            "id": "1",
            "activitySource": 1,
            "sourceData": {
                "uid": "eeedd3e9be41_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LWFnZW50LWZyYW1ld29yay1hcGktdjIuMS4wX19wYWdlLTE3Lm1k0_pages_0",
                "blob_url": "https://stassureds3vvlng2zilqy.blob.core.windows.net/cockpit-corpus/cockpit-agent-framework-api-v2.1.0__page-17.md",
                "snippet": "# cockpit-agent-framework-api v2.1.0 — Observabilidade\n\nConfiguração de observabilidade do componente **cockpit-agent-framework-api**, com foco em **OpenTelemetry**.",
            },
            "rerankerScore": 3.1628053,
            "docKey": "eeedd3e9be41_aHR0cHM6Ly9zdGFzc3VyZWRzM3Z2bG5nMnppbHF5LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jb2NrcGl0LWNvcnB1cy9jb2NrcGl0LWFnZW50LWZyYW1ld29yay1hcGktdjIuMS4wX19wYWdlLTE3Lm1k0_pages_0",
        },
    ],
    # answerSynthesis prose — NOT a JSON chunk array. The OLD join tried (and failed) to parse this.
    "response": [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Resumo curto: a plataforma usa OpenTelemetry e o componente cockpit-mcp-telemetry expõe telemetria consultável. [ref_id:0][ref_id:1]",
                }
            ],
        }
    ],
}

# A reference where sourceData exposes the chunk under `content` instead of `snippet` (extractedData-style
# KS): the fallback in _sourcedata_snippet must still recover it.
_CONTENT_FALLBACK_BODY = {
    "references": [
        {
            "id": "0",
            "sourceData": {
                "blob_url": "https://x.blob.core.windows.net/c/only-content-field__page-1.md",
                "content": "chunk text exposed under `content`, not `snippet`",
            },
            "docKey": "abc_" + "aHR0cHM6Ly94LmJsb2IuY29yZS53aW5kb3dzLm5ldC9jL29ubHktY29udGVudC1maWVsZF9fcGFnZS0xLm1k" + "_pages_0",
        }
    ],
    "response": [],
}


def _run() -> int:
    # 1) PRIMARY: every citation gets its snippet from references[].sourceData.snippet.
    rows = retrieval._parse_native(_LIVE_BODY)
    assert len(rows) == 2, rows
    for r in rows:
        assert r["snippet"], f"citation lost its snippet (the regression): {r}"
        assert r["url"].endswith(".md"), r  # docKey decode still yields the blob URL (untouched path)
        assert r["source"].endswith(".md"), r
    # The snippet is the ACTUAL source text (not the ref_id / prose), i.e. what the UI shows on click.
    assert rows[0]["snippet"].startswith("# cockpit-mcp-telemetry"), rows[0]
    assert "cockpit-mcp-telemetry" in rows[0]["source"], rows[0]
    assert rows[1]["snippet"].startswith("# cockpit-agent-framework-api"), rows[1]
    print(f"✅ PRIMARY: {len(rows)}/{len(rows)} citations carry non-empty sourceData.snippet")
    print(f"   e.g. source={rows[0]['source']!r} snippet[:60]={rows[0]['snippet'][:60]!r}")

    # 2) The full seam projection carries the snippet through (dedup + reindex in _project).
    projected = retrieval._project(rows)
    assert all(d["snippet"] for d in projected), projected
    assert [d["index"] for d in projected] == [1, 2], projected

    # 3) FALLBACK: sourceData.content is used when there's no `snippet` field.
    fb = retrieval._parse_native(_CONTENT_FALLBACK_BODY)
    assert len(fb) == 1 and fb[0]["snippet"] == "chunk text exposed under `content`, not `snippet`", fb
    print("✅ FALLBACK: sourceData.content recovered when `snippet` is absent")

    # 4) NEGATIVE (proves this test would have caught the regression): a null sourceData → empty snippet.
    empty_body = {"references": [{"id": "0", "sourceData": None, "docKey": _LIVE_BODY["references"][0]["docKey"]}]}
    empty_rows = retrieval._parse_native(empty_body)
    assert empty_rows and empty_rows[0]["snippet"] == "", empty_rows  # this is the OLD (broken) behavior
    print("✅ NEGATIVE: null sourceData → empty snippet (the exact regression this fix removes)")

    print("\n✅ native-path snippet fix holds: citations carry the per-source text (content-on-click restored)")
    return 0


def main() -> int:
    return _run()


if __name__ == "__main__":
    sys.exit(main())
