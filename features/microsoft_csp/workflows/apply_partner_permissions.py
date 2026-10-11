"""
Apply Permissions to Partner Tenant

Grants application permissions to the "Bifrost Microsoft" app in the MSP's own tenant.
This is a one-time setup step before rolling out to customer tenants.

IMPORTANT: Requires PIM elevation to Cloud Application Administrator (or similar)
before running. The GDAP delegated token doesn't have admin rights in your own
partner tenant by default.

Architecture:
- "Microsoft CSP" app: Used for delegated Partner Center/GDAP access
- "Microsoft" app: Used for client credentials to customer tenants (this is what we're granting permissions to)
"""

import logging

from bifrost import workflow, tables, context, UserError
from modules.extensions.platform_auth import require_platform_admin
from modules.extensions.microsoft_permission_policy import require_allowed_permissions

logger = logging.getLogger(__name__)

PERMISSIONS_TABLE = "microsoft_selected_permissions"
PENDING_REVOCATIONS_TABLE = "microsoft_pending_app_role_revocations"
MANAGED_ASSIGNMENTS_TABLE = "microsoft_managed_app_role_assignments"

# Well-known Microsoft API service principal IDs
MICROSOFT_APIS = {
    "00000003-0000-0000-c000-000000000000": "Microsoft Graph",
    "00000002-0000-0ff1-ce00-000000000000": "Exchange Online",
    "00000003-0000-0ff1-ce00-000000000000": "SharePoint",
    "fc780465-2017-40d4-a0c5-307022471b92": "Windows Defender ATP",
}


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "permissions", "partner"],
)
async def apply_partner_permissions(adopt_existing_assignments: bool = False) -> dict:
    """
    Apply selected application permissions to the "Bifrost Microsoft" app in the MSP's own tenant.

    This uses the GDAP delegated token (requires PIM elevation to Cloud Application Administrator)
    to grant application permissions to the Microsoft app's service principal.

    The Microsoft app is separate from the CSP app - it's used for client credentials
    access to customer tenants.

    PREREQUISITE: User must have PIM elevated to Cloud Application Administrator or similar
    role before running this workflow.

    Args:
        adopt_existing_assignments: Explicitly take ownership of matching grants
            that predate the managed-assignment ledger. For a pending
            deselection, the adopted grant is revoked in the same run.

    Returns:
        dict with success status and granted permissions
    """
    require_platform_admin()
    if type(adopt_existing_assignments) is not bool:
        raise UserError("adopt_existing_assignments must be true or false.")
    import httpx

    from modules.microsoft.auth import get_graph_token, get_microsoft_app_credentials

    org_id = context.org_id

    # Get selected permissions
    try:
        result = await tables.query(PERMISSIONS_TABLE, scope=org_id, limit=1000)
        all_permissions = [doc.data for doc in result.documents]
        pending_result = await tables.query(PENDING_REVOCATIONS_TABLE, scope=org_id, limit=1000)
        pending_revocations = [
            doc for doc in pending_result.documents if doc.data.get("pending")
        ]
    except Exception as e:
        raise UserError(f"Permission state could not be loaded. ({e})")
    if len(result.documents) >= 1000 or len(pending_result.documents) >= 1000:
        raise UserError("Permission state is too large to reconcile safely.")
    await require_allowed_permissions(all_permissions, org_id)

    if not all_permissions and not pending_revocations:
        raise UserError("No permissions configured. Please select permissions first.")

    # Filter to application permissions only (delegated are handled by Partner Center consent)
    app_permissions = [p for p in all_permissions if p.get("permission_type") == "application"]

    if not app_permissions and not pending_revocations:
        return {
            "success": True,
            "message": "No application permissions to grant",
            "granted_count": 0,
        }

    # Get the Microsoft app credentials (separate from CSP app)
    microsoft_app = await get_microsoft_app_credentials()
    microsoft_app_id = microsoft_app.client_id

    # Get delegated token for partner tenant (requires PIM elevation)
    # Using "common" will use the partner tenant since that's where the GDAP relationship is
    access_token = await get_graph_token(tenant_id="common")

    granted = []
    revoked = []
    adopted = []
    errors = []

    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # Find the Microsoft app's service principal in the partner tenant
        logger.info(f"Finding service principal for Microsoft app {microsoft_app_id}")
        
        sp_response = await client.get(
            f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{microsoft_app_id}')",
            headers=headers,
            timeout=30.0,
        )

        if sp_response.status_code == 404:
            raise UserError(
                f"Microsoft app service principal not found (appId={microsoft_app_id}). "
                f"Ensure the 'Bifrost Microsoft' app is registered in your tenant."
            )

        sp_response.raise_for_status()
        microsoft_sp = sp_response.json()
        microsoft_sp_id = microsoft_sp["id"]
        logger.info(f"Found Microsoft app SP: {microsoft_sp_id}")

        async def find_existing_assignment(perm: dict) -> tuple[str | None, str | None]:
            """Return the one exact Graph assignment for a configured permission."""
            api_id = perm.get("api_id")
            permission_name = perm.get("permission_name")
            resource_response = await client.get(
                f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{api_id}')",
                headers=headers,
                timeout=30.0,
            )
            if resource_response.status_code == 404:
                return None, "Resource service principal not found"
            resource_response.raise_for_status()
            resource_sp = resource_response.json()
            resource_sp_id = resource_sp.get("id")
            app_role_id = next(
                (
                    role.get("id")
                    for role in resource_sp.get("appRoles", [])
                    if role.get("value") == permission_name
                ),
                None,
            )
            if not resource_sp_id or not app_role_id:
                return None, "App role not found"

            check_response = await client.get(
                f"https://graph.microsoft.com/v1.0/servicePrincipals/{microsoft_sp_id}/appRoleAssignments",
                params={
                    "$filter": (
                        f"appRoleId eq {app_role_id} and resourceId eq {resource_sp_id}"
                    )
                },
                headers=headers,
                timeout=30.0,
            )
            check_response.raise_for_status()
            matches = [
                assignment
                for assignment in check_response.json().get("value", [])
                if assignment.get("appRoleId") == app_role_id
                and assignment.get("resourceId") == resource_sp_id
            ]
            if not matches:
                return None, None
            if len(matches) != 1 or not matches[0].get("id"):
                return None, "Matching Graph assignment is ambiguous"
            return matches[0]["id"], None

        # Revoke assignments recorded by this workflow. Older grants require an
        # explicit adoption flag so a platform admin deliberately takes
        # ownership before the workflow removes them.
        for pending in pending_revocations:
            perm = pending.data
            try:
                managed = await tables.get(
                    MANAGED_ASSIGNMENTS_TABLE, pending.id, scope=org_id
                )
            except Exception:
                managed = None
            if not managed or not managed.data.get("assignment_id"):
                if not adopt_existing_assignments:
                    errors.append({
                        "permission": perm.get("permission_name"),
                        "error": (
                            "Existing grant needs explicit ownership adoption "
                            "before revocation"
                        ),
                    })
                    continue
                assignment_id, lookup_error = await find_existing_assignment(perm)
                if lookup_error:
                    errors.append({
                        "permission": perm.get("permission_name"),
                        "error": lookup_error,
                    })
                    continue
                if not assignment_id:
                    await tables.delete(PENDING_REVOCATIONS_TABLE, pending.id, scope=org_id)
                    revoked.append({
                        "permission": perm.get("permission_name"),
                        "api": perm.get("api_name"),
                        "status": "already_absent",
                    })
                    continue
                await tables.upsert(
                    MANAGED_ASSIGNMENTS_TABLE,
                    id=pending.id,
                    data={
                        "assignment_id": assignment_id,
                        "api_id": perm.get("api_id"),
                        "permission_name": perm.get("permission_name"),
                    },
                    scope=org_id,
                )
                adopted.append({
                    "permission": perm.get("permission_name"),
                    "api": perm.get("api_name"),
                    "status": "adopted_for_revocation",
                })
            else:
                assignment_id = managed.data["assignment_id"]
            response = await client.delete(
                f"https://graph.microsoft.com/v1.0/servicePrincipals/{microsoft_sp_id}/appRoleAssignments/{assignment_id}",
                headers=headers,
                timeout=30.0,
            )
            if response.status_code == 404:
                replacement_id, lookup_error = await find_existing_assignment(perm)
                if lookup_error:
                    errors.append({
                        "permission": perm.get("permission_name"),
                        "error": lookup_error,
                    })
                    continue
                if replacement_id:
                    if not adopt_existing_assignments:
                        errors.append({
                            "permission": perm.get("permission_name"),
                            "error": (
                                "Tracked grant changed; explicit ownership adoption "
                                "is required before revocation"
                            ),
                        })
                        continue
                    await tables.upsert(
                        MANAGED_ASSIGNMENTS_TABLE,
                        id=pending.id,
                        data={
                            "assignment_id": replacement_id,
                            "api_id": perm.get("api_id"),
                            "permission_name": perm.get("permission_name"),
                        },
                        scope=org_id,
                    )
                    adopted.append({
                        "permission": perm.get("permission_name"),
                        "api": perm.get("api_name"),
                        "status": "adopted_replacement_for_revocation",
                    })
                    response = await client.delete(
                        f"https://graph.microsoft.com/v1.0/servicePrincipals/{microsoft_sp_id}/appRoleAssignments/{replacement_id}",
                        headers=headers,
                        timeout=30.0,
                    )
            if response.status_code not in (204, 404):
                errors.append({
                    "permission": perm.get("permission_name"),
                    "error": f"Graph revocation failed (HTTP {response.status_code})",
                })
                continue
            await tables.delete(MANAGED_ASSIGNMENTS_TABLE, pending.id, scope=org_id)
            await tables.delete(PENDING_REVOCATIONS_TABLE, pending.id, scope=org_id)
            revoked.append({"permission": perm.get("permission_name"), "api": perm.get("api_name")})

        # Group permissions by API
        by_api = {}
        for perm in app_permissions:
            api_id = perm.get("api_id")
            if api_id not in by_api:
                by_api[api_id] = []
            by_api[api_id].append(perm)

        # Process each API
        for api_id, perms in by_api.items():
            api_name = MICROSOFT_APIS.get(api_id, api_id)
            logger.info(f"Processing {len(perms)} app permissions for {api_name}")

            # Find the resource service principal
            resource_response = await client.get(
                f"https://graph.microsoft.com/v1.0/servicePrincipals(appId='{api_id}')",
                headers=headers,
                timeout=30.0,
            )

            if resource_response.status_code == 404:
                logger.warning(f"Resource SP not found for {api_name}")
                errors.append({"api": api_name, "error": "Service principal not found"})
                continue

            resource_response.raise_for_status()
            resource_sp = resource_response.json()
            resource_sp_id = resource_sp["id"]

            # Get available app roles from the resource
            app_roles = {role["value"]: role["id"] for role in resource_sp.get("appRoles", [])}

            # Grant each permission
            for perm in perms:
                perm_name = perm.get("permission_name")
                app_role_id = app_roles.get(perm_name)

                if not app_role_id:
                    logger.warning(f"App role not found: {perm_name}")
                    errors.append({"permission": perm_name, "error": "App role not found"})
                    continue

                # Check if already assigned
                check_response = await client.get(
                    f"https://graph.microsoft.com/v1.0/servicePrincipals/{microsoft_sp_id}/appRoleAssignments",
                    params={"$filter": f"appRoleId eq {app_role_id} and resourceId eq {resource_sp_id}"},
                    headers=headers,
                    timeout=30.0,
                )
                check_response.raise_for_status()

                existing = [
                    assignment
                    for assignment in check_response.json().get("value", [])
                    if assignment.get("appRoleId") == app_role_id
                    and assignment.get("resourceId") == resource_sp_id
                ]
                if existing:
                    assignment_key = f"{api_id}:{perm_name}:application"
                    try:
                        managed = await tables.get(
                            MANAGED_ASSIGNMENTS_TABLE, assignment_key, scope=org_id
                        )
                    except Exception:
                        managed = None
                    existing_ids = {
                        assignment.get("id")
                        for assignment in existing
                        if assignment.get("id")
                    }
                    managed_id = managed.data.get("assignment_id") if managed else None
                    if managed_id in existing_ids:
                        logger.info(f"Permission already granted and managed: {perm_name}")
                        granted.append({
                            "permission": perm_name,
                            "api": api_name,
                            "status": "already_granted",
                        })
                        continue
                    if len(existing_ids) != 1 or len(existing) != 1:
                        errors.append({
                            "permission": perm_name,
                            "error": "Matching Graph assignment is ambiguous",
                        })
                        continue
                    if not adopt_existing_assignments:
                        errors.append({
                            "permission": perm_name,
                            "error": (
                                "Existing grant is unmanaged; rerun with explicit "
                                "ownership adoption after review"
                            ),
                        })
                        continue
                    assignment_id = next(iter(existing_ids))
                    await tables.upsert(
                        MANAGED_ASSIGNMENTS_TABLE,
                        id=assignment_key,
                        data={
                            "assignment_id": assignment_id,
                            "api_id": api_id,
                            "permission_name": perm_name,
                        },
                        scope=org_id,
                    )
                    logger.info(f"Permission already granted: {perm_name}")
                    adopted.append({
                        "permission": perm_name,
                        "api": api_name,
                        "status": "adopted",
                    })
                    granted.append({
                        "permission": perm_name,
                        "api": api_name,
                        "status": "adopted",
                    })
                    continue

                # Grant the app role
                grant_response = await client.post(
                    f"https://graph.microsoft.com/v1.0/servicePrincipals/{resource_sp_id}/appRoleAssignedTo",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "principalId": microsoft_sp_id,
                        "resourceId": resource_sp_id,
                        "appRoleId": app_role_id,
                    },
                    timeout=30.0,
                )

                if grant_response.status_code in [200, 201]:
                    logger.info(f"Granted permission: {perm_name}")
                    granted.append({"permission": perm_name, "api": api_name, "status": "granted"})
                    assignment_id = grant_response.json().get("id")
                    if not assignment_id:
                        errors.append({"permission": perm_name, "error": "Graph grant ID missing; ownership tracking failed"})
                    else:
                        await tables.upsert(
                            MANAGED_ASSIGNMENTS_TABLE,
                            id=f"{api_id}:{perm_name}:application",
                            data={"assignment_id": assignment_id, "api_id": api_id, "permission_name": perm_name},
                            scope=org_id,
                        )
                else:
                    error_text = grant_response.text
                    # "Permission being assigned already exists" is actually success
                    if "already exists" in error_text.lower():
                        errors.append({
                            "permission": perm_name,
                            "api": api_name,
                            "error": (
                                "Graph reported an existing grant without a verified "
                                "assignment ID; rerun reconciliation"
                            ),
                        })
                    else:
                        logger.error(f"Failed to grant {perm_name}: {error_text}")
                        errors.append({"permission": perm_name, "api": api_name, "error": error_text})

    return {
        "success": len(errors) == 0,
        "granted_count": len(granted),
        "revoked_count": len(revoked),
        "adopted_count": len(adopted),
        "revoked": revoked,
        "adopted": adopted,
        "granted": granted,
        "errors": errors if errors else None,
    }
