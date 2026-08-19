"""Microsoft Graph client (app-only) for user + app-role management.

The admin portal drives all user/role operations through Graph with the API app's OWN
identity (client credentials) — no parallel user store. Every caller of these functions is
gated by the server-side `Admin` role (app/api/admin.py); the app-only token is what lets the
app act regardless of which admin called.

Requires the API app to hold app-only Graph permissions, admin-consented:
  User.ReadWrite.All, User.Invite.All, AppRoleAssignment.ReadWrite.All, Directory.Read.All
(see scripts/setup-app-roles.sh). App roles are assigned to a *user* on this free tenant; the
same call assigns to a *group* once the tenant has Entra ID P1.

SDK note: plain Graph REST via urllib (matches app/agents/secure_search.py); token via
azure-identity ClientSecretCredential.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

from azure.identity import ClientSecretCredential

from app.shared.auth import APP_ROLES
from app.shared.settings import settings

_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = "https://graph.microsoft.com/.default"


def _token() -> str:
    # Missing configuration is a GraphError, not a crash. `ClientSecretCredential` raises a bare
    # `ValueError("client_id should be the id of a Microsoft Entra application")` when handed an
    # empty client id — and that is not a GraphError, so it sails past `_guard` and reaches the
    # browser as an opaque 500. Which is exactly what /admin/users did on any environment without
    # Entra wired: a page that cannot work, failing in a way that tells nobody why.
    #
    # The same escape route was already patched once in `_graph` (see the URL-encoding note
    # below); this is the other door into it.
    missing = [
        name
        for name, value in (
            ("ENTRA_TENANT_ID", settings.entra_tenant_id),
            ("ENTRA_API_CLIENT_ID", settings.entra_api_client_id),
            ("ENTRA_API_CLIENT_SECRET", settings.entra_api_client_secret),
        )
        if not value
    ]
    if missing:
        raise GraphError(
            503,
            "User management needs Microsoft Graph app-only credentials, and "
            f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set. "
            "Run ./scripts/setup-entra.sh, or use this environment without the admin pages.",
        )

    cred = ClientSecretCredential(
        tenant_id=settings.entra_tenant_id,
        client_id=settings.entra_api_client_id,
        client_secret=settings.entra_api_client_secret,
    )
    return cred.get_token(_SCOPE).token


def _graph(method: str, path: str, body: dict | None = None) -> dict | None:
    """One Graph REST call. Raises GraphError(status, message) on failure."""
    url = path if path.startswith("http") else f"{_GRAPH}{path}"
    # OData $filter clauses contain literal spaces (e.g. "appId eq '…'"); urllib rejects raw
    # spaces in a URL with InvalidURL ("control characters"). Percent-encode them (and the
    # single quotes) so the request is built — otherwise a non-GraphError escapes _guard → 500.
    url = url.replace(" ", "%20").replace("'", "%27")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, method=method, data=data,
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:  # surface Graph's error message
        detail = e.read().decode(errors="ignore")
        try:
            detail = json.loads(detail).get("error", {}).get("message", detail)
        except Exception:  # noqa: BLE001, S110 — corpo de erro sem JSON válido: mantém o texto
            # cru e segue para levantar o GraphError de qualquer forma; não há o que logar aqui
            # que o `raise` logo abaixo já não carregue.
            pass
        raise GraphError(e.code, detail) from e


class GraphError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"Graph {status}: {message}")


# --- Service principal of the API app (where app roles + assignments live) ----

@lru_cache(maxsize=1)
def _api_sp_id() -> str:
    """Object id of the API app's service principal (cached)."""
    appid = settings.entra_api_client_id
    res = _graph("GET", f"/servicePrincipals?$filter=appId eq '{appid}'&$select=id")
    vals = (res or {}).get("value", [])
    if not vals:
        raise GraphError(404, f"no service principal for appId {appid}")
    return vals[0]["id"]


@lru_cache(maxsize=1)
def _app_role_ids() -> dict[str, str]:
    """Map appRole displayName/value → id, from the API app's service principal."""
    sp = _graph("GET", f"/servicePrincipals/{_api_sp_id()}?$select=appRoles")
    out: dict[str, str] = {}
    for r in (sp or {}).get("appRoles", []):
        if r.get("isEnabled"):
            out[r.get("value") or r.get("displayName")] = r["id"]
    return out


# --- Users (lifecycle) --------------------------------------------------------

def list_users(top: int = 50) -> list[dict]:
    res = _graph("GET", f"/users?$top={top}&$select=id,displayName,userPrincipalName,mail,accountEnabled")
    return (res or {}).get("value", [])


def invite_user(email: str, redirect_url: str, send_email: bool = True) -> dict:
    """Invite an external user (B2B guest)."""
    body = {
        "invitedUserEmailAddress": email,
        "inviteRedirectUrl": redirect_url,
        "sendInvitationMessage": send_email,
    }
    return _graph("POST", "/invitations", body) or {}


def create_user(display_name: str, user_principal_name: str, password: str) -> dict:
    """Create an internal member user. Caller supplies a temporary password."""
    body = {
        "accountEnabled": True,
        "displayName": display_name,
        "userPrincipalName": user_principal_name,
        "mailNickname": user_principal_name.split("@", 1)[0],
        "passwordProfile": {"forceChangePasswordNextSignIn": True, "password": password},
    }
    return _graph("POST", "/users", body) or {}


def delete_user(user_id: str) -> None:
    _graph("DELETE", f"/users/{user_id}")


# --- App-role assignments (who has which role) --------------------------------

def list_role_assignments() -> list[dict]:
    """Current app-role assignments on the API app → [{id, principalId, principalDisplayName, role}]."""
    sp = _api_sp_id()
    res = _graph("GET", f"/servicePrincipals/{sp}/appRoleAssignedTo")
    id_to_role = {v: k for k, v in _app_role_ids().items()}
    out = []
    for a in (res or {}).get("value", []):
        out.append({
            "id": a["id"],
            "principalId": a.get("principalId"),
            "principalDisplayName": a.get("principalDisplayName"),
            "principalType": a.get("principalType"),
            "role": id_to_role.get(a.get("appRoleId"), a.get("appRoleId")),
        })
    return out


def assign_role(principal_id: str, role: str) -> dict:
    """Assign an app role to a principal (user or group). The Graph call is identical for
    both — group assignment just needs the tenant to have Entra ID P1."""
    if role not in APP_ROLES:
        raise GraphError(400, f"unknown role '{role}' (valid: {', '.join(APP_ROLES)})")
    role_id = _app_role_ids().get(role)
    if not role_id:
        raise GraphError(409, f"role '{role}' not declared on the app registration yet")
    sp = _api_sp_id()
    body = {"principalId": principal_id, "resourceId": sp, "appRoleId": role_id}
    return _graph("POST", f"/servicePrincipals/{sp}/appRoleAssignedTo", body) or {}


def revoke_role(assignment_id: str) -> None:
    sp = _api_sp_id()
    _graph("DELETE", f"/servicePrincipals/{sp}/appRoleAssignedTo/{assignment_id}")
