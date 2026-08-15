"""The doc-bundle manifest CONTRACT — vendored from the producer, enforced here.

`manifest.json` is not our format: it is defined by the doc-bundle producer (the
the producer's `Manifest` model), and this repo both READS bundles
(`ingest_docbundles`, `wiki_freshness_test`) and WRITES them (`wiki_builder`,
`adapt_deepwiki`, and by hand via the vendored deep-wiki skill). Two repos, one
format, no shared package — which is exactly how it forked once already: the
ingest started reading `groups` for per-document ACL while the producer's model
had no such field, and the local writer grew its own format instead of the
common one.

So the contract travels as **data**: `docbundle.schema.json` is generated from
the producer's model and copied here byte-for-byte. Every manifest this repo
writes is validated against it *before* it hits disk, so a divergence fails at
the generator instead of surfacing as an empty ACL months later.

Semantics that matter to us, straight from the contract (see `groups`):

    null / absent → the bundle declares NO access; the ingest decides (external
                    map, tenant default, or the source's native ACL)
    []            → the bundle declares that NO group may read it (explicit
                    fail-closed)

They are different statements, and the ingest treats them differently. A writer
that emits `[]` because it has nothing to say is lying about access.

Drift: this file is a copy. `eval/docbundle_contract_test.py` is the guard — it
checks what we read and write against it, and, when `DOCBUNDLE_SCHEMA_REF`
points at the producer's copy, that this one is still identical to it.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("docbundle.schema.json")

#: Env var naming the producer's own `docbundle.schema.json` (a checkout of the
#: producing repo). Set it to have the guard compare our copy against the source.
SCHEMA_REF_ENV = "DOCBUNDLE_SCHEMA_REF"


@lru_cache(maxsize=1)
def load_schema() -> dict:
    """The vendored manifest contract."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def producer_schema_path() -> Path | None:
    """The producer's copy, when a local checkout is pointed at by the env var."""
    ref = os.environ.get(SCHEMA_REF_ENV, "").strip()
    if not ref:
        return None
    return Path(ref).expanduser()


def manifest_fields() -> set[str]:
    """Top-level field names the contract defines (the on-disk camelCase names)."""
    return set(load_schema()["properties"])


def page_fields() -> set[str]:
    """Field names of one entry of `pages[]`."""
    return set(load_schema()["$defs"]["PageMeta"]["properties"])


def validate_manifest(manifest: dict) -> None:
    """Raise `ValueError` if `manifest` does not satisfy the contract.

    Uses the official `jsonschema` validator — the format is a shared contract,
    and a hand-rolled check would just encode this repo's reading of it.
    """
    import jsonschema

    validator = jsonschema.Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.path))
    if not errors:
        return
    detail = "; ".join(
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
    )
    raise ValueError(f"manifest violates the doc-bundle contract ({SCHEMA_PATH.name}): {detail}")
