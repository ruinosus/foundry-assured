"""User and role administration over Microsoft Graph (app-only).

`GraphError` is public because callers map it to HTTP status; the Graph calls themselves are
reached through the module's own routers.
"""

from app.modules.admin.internal.graph import GraphError

__all__ = ["GraphError"]
