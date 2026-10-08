"""
Save Selected Microsoft Permissions

Saves the user's selected permissions to the microsoft_selected_permissions table.
Required bootstrap permissions are always included regardless of user selection.
"""

import logging
from datetime import datetime, timezone

from bifrost import workflow, tables, context, UserError
from modules.extensions.platform_auth import require_platform_admin

logger = logging.getLogger(__name__)

PERMISSIONS_TABLE = "microsoft_selected_permissions"
PENDING_REVOCATIONS_TABLE = "microsoft_pending_app_role_revocations"

# Required delegated permissions - needed to install app permissions
# These are always included and cannot be deselected
REQUIRED_DELEGATED_PERMISSIONS = [
    {
        "api_id": "00000003-0000-0000-c000-000000000000",
        "api_name": "Microsoft Graph",
        "permission_name": "Directory.ReadWrite.All",
        "permission_type": "delegated",
        "required": True,
    },
    {
        "api_id": "00000003-0000-0000-c000-000000000000",
        "api_name": "Microsoft Graph",
        "permission_name": "AppRoleAssignment.ReadWrite.All",
        "permission_type": "delegated",
        "required": True,
    },
]


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "permissions"],
)
async def save_selected_permissions(
    permissions: list[dict],
) -> dict:
    """
    Save selected Microsoft permissions.

    Required bootstrap permissions (Directory.ReadWrite.All, AppRoleAssignment.ReadWrite.All)
    are automatically included even if not in the input list.

    Args:
        permissions: List of permission dicts with:
            - api_id: Enterprise application ID
            - api_name: Display name (e.g., "Microsoft Graph")
            - permission_name: Permission value (e.g., "User.Read.All")
            - permission_type: "delegated" or "application"

    Returns:
        Success status and count
    """
    require_platform_admin()
    if permissions is None:
        permissions = []

    # Validate permission structure
    for perm in permissions:
        if not all(k in perm for k in ["api_id", "api_name", "permission_name", "permission_type"]):
            raise UserError(f"Invalid permission structure: {perm}")
        if perm["permission_type"] not in ["delegated", "application"]:
            raise UserError(f"Invalid permission_type: {perm['permission_type']}")

    # Get platform org scope
    org_id = context.org_id

    # Build final permissions list, ensuring required permissions are included
    final_permissions = []
    
    # Track what's been added to avoid duplicates
    added_keys = set()
    
    # Add required permissions first
    for req_perm in REQUIRED_DELEGATED_PERMISSIONS:
        key = f"{req_perm['api_id']}:{req_perm['permission_name']}:{req_perm['permission_type']}"
        if key not in added_keys:
            final_permissions.append(req_perm)
            added_keys.add(key)
    
    # Add user-selected permissions (skip if already added as required)
    for perm in permissions:
        key = f"{perm['api_id']}:{perm['permission_name']}:{perm['permission_type']}"
        if key not in added_keys:
            # Mark as not required
            perm_with_flag = {**perm, "required": False}
            final_permissions.append(perm_with_flag)
            added_keys.add(key)

    # Retain deselected application roles until the external assignment has
    # actually been removed. Losing this intent would leave a silent grant.
    await tables.upsert(
        PENDING_REVOCATIONS_TABLE,
        id="__initialized__",
        data={"pending": False},
        scope=org_id,
    )
    selected_keys = {
        (p["api_id"], p["permission_name"])
        for p in final_permissions if p["permission_type"] == "application"
    }

    # Clear existing permissions and save new ones
    try:
        existing = await tables.query(PERMISSIONS_TABLE, scope=org_id, limit=1000)
    except Exception as e:
        raise UserError("Existing permissions could not be loaded safely.") from e
    if len(existing.documents) >= 1000:
        raise UserError("Existing permission set is too large to replace safely.")
    for doc in existing.documents:
        old = doc.data
        if old.get("permission_type") == "application" and (
            old.get("api_id"), old.get("permission_name")
        ) not in selected_keys:
            await tables.upsert(
                PENDING_REVOCATIONS_TABLE,
                id=doc.id,
                data={**old, "pending": True},
                scope=org_id,
            )
    for doc in existing.documents:
        await tables.delete(PERMISSIONS_TABLE, doc.id, scope=org_id)

    # A reselected role must not be revoked by an older pending entry.
    for api_id, permission_name in selected_keys:
        await tables.delete(
            PENDING_REVOCATIONS_TABLE,
            f"{api_id}:{permission_name}:application",
            scope=org_id,
        )

    # Save new permissions
    now = datetime.now(timezone.utc).isoformat()
    saved_count = 0

    for perm in final_permissions:
        # Create unique ID from api_id + permission_name + type
        perm_id = f"{perm['api_id']}:{perm['permission_name']}:{perm['permission_type']}"

        await tables.upsert(
            PERMISSIONS_TABLE,
            id=perm_id,
            data={
                "api_id": perm["api_id"],
                "api_name": perm["api_name"],
                "permission_name": perm["permission_name"],
                "permission_type": perm["permission_type"],
                "required": perm.get("required", False),
                "created_at": now,
            },
            scope=org_id,
        )
        saved_count += 1

    logger.info(f"Saved {saved_count} permissions ({len(REQUIRED_DELEGATED_PERMISSIONS)} required)")

    return {
        "success": True,
        "saved_count": saved_count,
        "required_count": len(REQUIRED_DELEGATED_PERMISSIONS),
    }
