"""DEPRECATED shim — this module was renamed to ``app.knowledge.ingest_docbundles``.

The docbundle→KB ingest is GENERIC (it serves the cockpit AND selfwiki corpora), so the
``_cockpit`` name was misleading. This thin re-export keeps existing callers working for one
release — both ``from app.knowledge.ingest_cockpit import ...`` and the CLI
``python -m app.knowledge.ingest_cockpit [--selfwiki]``. Prefer ``ingest_docbundles``.
"""

from app.knowledge.ingest_docbundles import *  # noqa: F401,F403 (back-compat re-export)
from app.knowledge.ingest_docbundles import main  # noqa: F401

if __name__ == "__main__":
    main()
