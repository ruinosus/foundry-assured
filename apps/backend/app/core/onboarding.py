"""The onboarding guard — gates self-service tenant creation.

Separate from require_user (which resolves the tenant and would 403 pre-onboarding). It
authenticates via the scheme, stashes the user in the contextvar (so the handler reads the tid),
and checks the two gates — Admin app role (granted by the customer's Entra) AND the platform
allow-list (we control it) — but does NOT resolve the tenant.
"""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi_azure_auth.user import User

from app.core.auth import _current_user, azure_scheme
from app.core.settings import settings


def onboarding_guard(user: User = Security(azure_scheme)) -> User:  # type: ignore[arg-type]
    _current_user.set(user)  # so POST /onboard reads the caller's tid
    if "Admin" not in (getattr(user, "roles", None) or []):
        raise HTTPException(status_code=403, detail="requires Admin")
    if getattr(user, "tid", None) not in settings.allowed_tids:
        raise HTTPException(status_code=403, detail="tenant not allow-listed")
    return user
