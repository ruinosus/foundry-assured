"""Contract gate — this repo and the doc-bundle producer must agree on the fields.

The failure this exists to prevent already happened once: the ingest started reading
`manifest["groups"]` to stamp per-document ACL, the producer's model never had the field,
nobody noticed (a missing key just reads as "no access declared"), and the local pipeline
ended up growing its own generator of the same format. Two writers, one silent divergence,
zero failing tests.

So: `app/modules/knowledge/internal/docbundle.schema.json` is the producer's contract, vendored here, and
this gate checks BOTH directions against it —

  1. every manifest field this repo READS exists in the contract (the direction that broke);
  2. every manifest field this repo WRITES exists in the contract (so a local generator
     cannot quietly invent a dialect);
  3. the bundles committed under `docs/wiki/` still validate (real artifacts, not fixtures);
  4. `[]` and null are distinguishable end to end — the ingest must treat "declares no
     group" and "declares nothing" differently, because one is an ACL and the other isn't.

(1) and (2) read the field names out of the source with `ast`, rather than from a list
maintained by hand: a list is exactly the thing that goes stale while staying green.

Cross-repo drift: the vendored schema is a copy. Point `DOCBUNDLE_SCHEMA_REF` at the
producer's own `docbundle.schema.json` (in a local checkout of that repo) and check (0)
verifies the copy is still byte-identical. Without it, that one check is skipped and
reported as skipped — it never passes silently.

    uv run python -m eval.docbundle_contract_test
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

from app.modules.knowledge.internal import docbundle_schema

_BACKEND = Path(__file__).resolve().parents[1]
_KNOWLEDGE = _BACKEND / "app" / "modules" / "knowledge" / "internal"  # ADR-017 moved it here
_WIKI = _BACKEND.parents[1] / "docs" / "wiki"

# Modules that touch a manifest, and the local variable each one binds it to. Reading a
# manifest is always "load the json, then poke at a dict" — so the variable name is the
# only anchor. Kept explicit (and asserted non-empty below) so an unlisted module shows
# up as a suspiciously small read-set rather than as silence.
_READERS: dict[Path, dict[str, str]] = {
    _KNOWLEDGE / "ingest_docbundles.py": {"meta": "manifest", "page": "page"},
    _BACKEND / "eval" / "wiki_freshness_test.py": {"meta": "manifest"},
}
# Modules that BUILD a manifest, and the name of the dict they build it into.
_WRITERS: dict[Path, str] = {
    _KNOWLEDGE / "wiki_builder.py": "manifest",
    _KNOWLEDGE / "adapt_deepwiki.py": "manifest",
}

# Fields whose loss would be invisible in the read-set derivation (a rename, a refactor to
# a helper) but fatal in production. Asserted present so the derivation cannot go blind.
_MUST_BE_READ = {"groups", "component", "pages"}


def _read_fields(path: Path, binding: dict[str, str]) -> dict[str, set[str]]:
    """Keys read off the named variables: `x.get("k")` / `x["k"]` → {kind: {keys}}."""
    found: dict[str, set[str]] = {kind: set() for kind in binding.values()}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        target = key = None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            target, key = node.func.value.id, node.args[0].value
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            target, key = node.value.id, node.slice.value
        if target in binding and key:
            found[binding[target]].add(key)
    return found


def _written_fields(path: Path, var: str) -> set[str]:
    """Keys of the manifest dict literal assigned to `var` (top level of the dict)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(t, ast.Name) and t.id == var for t in node.targets):
            continue
        keys |= {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def _check_vendored_copy() -> tuple[int, int]:
    """(failures, skips) — the vendored contract must equal the producer's."""
    ref = docbundle_schema.producer_schema_path()
    if ref is None:
        print(f"⏭️  0. vendored copy vs producer — SKIPPED (set {docbundle_schema.SCHEMA_REF_ENV})")
        return 0, 1
    if not ref.is_file():
        print(f"❌ 0. {docbundle_schema.SCHEMA_REF_ENV} does not point at a file: {ref}")
        return 1, 0
    ours = docbundle_schema.SCHEMA_PATH.read_bytes()
    if ours != ref.read_bytes():
        print(
            "❌ 0. the vendored contract drifted from the producer's — re-copy it:\n"
            f"      cp {ref} {docbundle_schema.SCHEMA_PATH}"
        )
        return 1, 0
    print("✅ 0. vendored contract identical to the producer's")
    return 0, 0


def main() -> int:
    failures, skips = _check_vendored_copy()
    manifest_fields = docbundle_schema.manifest_fields()
    page_fields = docbundle_schema.page_fields()

    # 1. what we READ must exist in the contract.
    read_manifest: set[str] = set()
    for path, binding in _READERS.items():
        found = _read_fields(path, binding)
        read_manifest |= found.get("manifest", set())
        unknown_pages = found.get("page", set()) - page_fields
        if unknown_pages:
            failures += 1
            print(f"❌ 1. {path.name} reads page field(s) absent from the contract: {sorted(unknown_pages)}")
    unknown = read_manifest - manifest_fields
    if unknown:
        failures += 1
        print(
            f"❌ 1. manifest field(s) read here but NOT in the contract: {sorted(unknown)}\n"
            "      → add them to the producer's Manifest and re-copy the schema; do NOT "
            "fork the format."
        )
    missing_anchor = _MUST_BE_READ - read_manifest
    if missing_anchor:
        failures += 1
        print(
            f"❌ 1. the read-set derivation went blind: expected to see {sorted(missing_anchor)} "
            "being read. Did a reader move or get renamed? Update _READERS."
        )
    if not unknown and not missing_anchor:
        print(f"✅ 1. {len(read_manifest)} manifest field(s) read here, all in the contract")

    # 2. what we WRITE must exist in the contract.
    for path, var in _WRITERS.items():
        written = _written_fields(path, var)
        if not written:
            failures += 1
            print(f"❌ 2. found no manifest literal in {path.name} — _WRITERS is stale")
            continue
        invented = written - manifest_fields
        if invented:
            failures += 1
            print(f"❌ 2. {path.name} writes field(s) not in the contract: {sorted(invented)}")
        else:
            print(f"✅ 2. {path.name} writes {len(written)} field(s), all in the contract")

    # 3. the committed bundles still satisfy the contract.
    manifests = sorted(_WIKI.rglob("manifest.json")) if _WIKI.is_dir() else []
    if not manifests:
        print("⏭️  3. no committed bundles under docs/wiki — SKIPPED")
        skips += 1
    else:
        bad = 0
        for m in manifests:
            try:
                docbundle_schema.validate_manifest(json.loads(m.read_text(encoding="utf-8")))
            except ValueError as exc:
                bad += 1
                failures += 1
                print(f"❌ 3. {m.relative_to(_WIKI.parent)}: {exc}")
        if not bad:
            print(f"✅ 3. {len(manifests)} committed bundle(s) validate against the contract")

    # 4. absent ≠ empty, proven through the real reader. Imported late: it pulls the
    # azure SDKs, and checks 0-3 are pure file reads.
    from app.modules.knowledge.internal.ingest_docbundles import collect_pages

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, groups in (("declares-nothing", None), ("declares-nobody", [])):
            d = root / name
            (d / "pages").mkdir(parents=True)
            (d / "pages" / "page-1.md").write_text("# t\nx\n", encoding="utf-8")
            (d / "manifest.json").write_text(
                json.dumps({
                    "key": name, "title": name,
                    "source": {"type": "repo", "ref": "", "commit": ""},
                    "kind": "element", "component": name, "componentVersion": "v1",
                    "releaseVersion": None, "groups": groups,
                    "pages": [{"id": "page-1", "title": "t", "order": 1,
                               "file": "pages/page-1.md", "audience": "base"}],
                }),
                encoding="utf-8",
            )
        _, access = collect_pages(root)
        if "declares-nothing" in access:
            failures += 1
            print("❌ 4. a manifest that declares NO access entered the ACL map (absent read as a declaration)")
        elif access.get("declares-nobody") != []:
            failures += 1
            print(f"❌ 4. an explicit `groups: []` did not survive as [] (got {access.get('declares-nobody')!r}) "
                  "— fail-closed silently became the default audience")
        else:
            print("✅ 4. absent stays undeclared, [] stays an explicit (fail-closed) declaration")

    print()
    if failures:
        print(f"❌ doc-bundle contract: {failures} failure(s).")
        return 1
    print(f"✅ doc-bundle contract: all checks passed{f' ({skips} skipped)' if skips else ''}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
