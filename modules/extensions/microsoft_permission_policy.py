"""Operator-owned allowlist for Microsoft consent and application grants."""

import json

from bifrost import config, UserError


POLICY_KEY = "microsoft_allowed_permissions"
MICROSOFT_API_IDS = {
    "00000003-0000-0000-c000-000000000000",
    "00000002-0000-0ff1-ce00-000000000000",
    "fc780465-2017-40d4-a0c5-307022471b92",
}
REQUIRED_DELEGATED = {
    ("00000003-0000-0000-c000-000000000000", "Directory.ReadWrite.All", "delegated"),
    ("00000003-0000-0000-c000-000000000000", "AppRoleAssignment.ReadWrite.All", "delegated"),
}


async def require_allowed_permissions(permissions: list[dict], scope: str) -> None:
    """Reject every permission absent from the destination's explicit policy."""
    raw = await config.get(POLICY_KEY, default="[]", scope=scope)
    try:
        entries = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as error:
        raise UserError("Microsoft permission allowlist is invalid.") from error
    if not isinstance(entries, list):
        raise UserError("Microsoft permission allowlist must be a list.")

    allowed = set(REQUIRED_DELEGATED)
    for entry in entries:
        if not isinstance(entry, dict):
            raise UserError("Microsoft permission allowlist entry is invalid.")
        key = (entry.get("api_id"), entry.get("permission_name"), entry.get("permission_type"))
        if (
            key[0] not in MICROSOFT_API_IDS
            or not isinstance(key[1], str) or not key[1].strip()
            or key[2] not in ("delegated", "application")
        ):
            raise UserError("Microsoft permission allowlist entry is invalid.")
        allowed.add(key)

    for permission in permissions:
        key = (
            permission.get("api_id"),
            permission.get("permission_name"),
            permission.get("permission_type"),
        )
        if key not in allowed:
            raise UserError("Microsoft permission is not approved by the platform policy.")
