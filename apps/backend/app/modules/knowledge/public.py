"""Knowledge: ingestion, corpus, wiki generation, per-document ACL, and retrieval.

The ACL is this module's most important export and RULE #6's home: access control is DATA
(the read groups declared on each source), never classification logic. `trim_agentic_content`
and `authorized_components` are the enforcement points, and they run BEFORE the model sees
anything — which is why no client-facing protocol could ever own them (ADR-018).

`_chunk_component` and `_decode_dockey` were private-by-name but imported across the old layer
boundary, so they are named for what they are. ADR-017 asked for exactly this: promote what is
really public surface instead of leaving an underscore that lies.
"""

from app.modules.knowledge.internal.retrieval import _decode_dockey as decode_dockey
from app.modules.knowledge.internal.retrieval import retrieve
from app.modules.knowledge.internal.secure_search import (
    _chunk_component as chunk_component,
)
from app.modules.knowledge.internal.secure_search import (
    authorized_components,
    trim_agentic_content,
)

__all__ = [
    "authorized_components",
    "chunk_component",
    "decode_dockey",
    "retrieve",
    "trim_agentic_content",
]
