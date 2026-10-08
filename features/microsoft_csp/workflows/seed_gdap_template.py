"""
Seed GDAP Template

One-time setup workflow: fetches security group -> role mappings from an existing
GDAP relationship and stores them in the gdap_template table.

After seeding, the template is managed via the CSP app UI.
"""

import logging
import hashlib
import json

from bifrost import workflow, tables, context, UserError
from modules.extensions.platform_auth import require_platform_admin

from modules.microsoft.auth import get_graph_token
from modules.microsoft.graph import GraphClient
from modules.microsoft import gdap

logger = logging.getLogger(__name__)

TEMPLATE_TABLE = "gdap_template"


@workflow(
    category="Microsoft CSP",
    tags=["gdap", "template", "setup"],
)
async def seed_gdap_template(
    relationship_id: str | None = None,
    tenant_id: str | None = None,
    confirmation_digest: str | None = None,
) -> dict:
    """
    Seed the GDAP template from an existing relationship's assignments.

    Fetches the access assignments (security group -> role mappings) from the
    specified relationship and stores them in the gdap_template table.

    Provide either relationship_id directly, or tenant_id to auto-find the
    best active relationship for that tenant.

    Args:
        relationship_id: ID of an existing GDAP relationship to use as template
        tenant_id: Customer tenant ID (auto-finds active relationship)

    Returns:
        dict with count of groups seeded
    """
    require_platform_admin()
    if not relationship_id and not tenant_id:
        raise UserError("Provide either relationship_id or tenant_id")

    token = await get_graph_token("common")
    graph = GraphClient(token)

    # Resolve relationship from tenant_id if needed
    if not relationship_id:
        relationships = gdap.list_relationships(graph, tenant_id=tenant_id)
        best = gdap.find_best_relationship(relationships)
        if not best:
            raise UserError(f"No GDAP relationship found for tenant {tenant_id}")
        if best.get("status") != "active":
            raise UserError(
                f"Best relationship for tenant is '{best.get('status')}', "
                "must be 'active' to read assignments"
            )
        relationship_id = best["id"]

    # Verify relationship exists
    relationship = gdap.get_relationship(graph, relationship_id)
    if not relationship:
        raise UserError(f"GDAP relationship {relationship_id} not found")

    status = relationship.get("status")
    if status != "active":
        raise UserError(
            f"Relationship is '{status}', must be 'active' to read assignments"
        )

    # Fetch assignments
    assignments = gdap.list_assignments(graph, relationship_id)
    if not assignments:
        raise UserError("No active assignments found on this relationship")

    # Resolve security group names via Graph API
    group_ids = [
        a["accessContainer"]["accessContainerId"] for a in assignments
    ]

    group_names = {}
    for gid in group_ids:
        try:
            group = graph.get(f"/groups/{gid}", params={"$select": "displayName"})
            group_names[gid] = group.get("displayName", gid)
        except Exception:
            group_names[gid] = gid

    # Resolve role names
    role_names = {}
    try:
        roles = graph.paginate("/directoryRoles", params={"$select": "roleTemplateId,displayName"})
        for role in roles:
            template_id = role.get("roleTemplateId")
            if template_id:
                role_names[template_id] = role.get("displayName", template_id)
    except Exception:
        pass  # Role names are cosmetic, not critical

    # Compute the new rows first. No delete occurs until the caller confirms a
    # digest of both the existing table and the proposed replacement.
    provider_org_id = context.org_id
    proposed = {}
    for assignment in assignments:
        group_id = assignment["accessContainer"]["accessContainerId"]
        unified_roles = assignment["accessDetails"].get("unifiedRoles", [])

        # Enrich roles with display names
        enriched_roles = []
        for role in unified_roles:
            role_def_id = role.get("roleDefinitionId", "")
            enriched_roles.append({
                "roleDefinitionId": role_def_id,
                "roleName": role_names.get(role_def_id, role_def_id),
            })

        if group_id in proposed:
            raise UserError("Duplicate GDAP group assignments cannot seed a template")
        proposed[group_id] = {
                "security_group_id": group_id,
                "security_group_name": group_names.get(group_id, group_id),
                "unified_roles": enriched_roles,
                "enabled": True,
            }

    existing = await tables.query(TEMPLATE_TABLE, scope=provider_org_id, limit=1000)
    if len(existing.documents) >= 1000:
        raise UserError("GDAP template is too large for a safe replacement preview")
    current = {doc.id: doc.data for doc in existing.documents}
    snapshot = json.dumps(
        {"relationship_id": relationship_id, "current": current, "proposed": proposed},
        sort_keys=True, separators=(",", ":"),
    )
    digest = hashlib.sha256(snapshot.encode()).hexdigest()
    if confirmation_digest is None:
        return {
            "success": True,
            "preview": True,
            "source_relationship_id": relationship_id,
            "current_groups": sorted(current),
            "proposed_groups": sorted(proposed),
            "confirmation_digest": digest,
        }
    if confirmation_digest != digest:
        raise UserError("GDAP template changed since preview; review a new plan")

    latest = await tables.query(TEMPLATE_TABLE, scope=provider_org_id, limit=1000)
    latest_snapshot = json.dumps(
        {
            "relationship_id": relationship_id,
            "current": {doc.id: doc.data for doc in latest.documents},
            "proposed": proposed,
        },
        sort_keys=True, separators=(",", ":"),
    )
    if hashlib.sha256(latest_snapshot.encode()).hexdigest() != digest:
        raise UserError("GDAP template changed since preview; review a new plan")

    for doc in latest.documents:
        await tables.delete(TEMPLATE_TABLE, id=doc.id, scope=provider_org_id)
    for group_id, data in proposed.items():
        await tables.upsert(TEMPLATE_TABLE, id=group_id, data=data, scope=provider_org_id)
    seeded = len(proposed)

    logger.info(f"Seeded {seeded} security group assignments to GDAP template")

    return {
        "success": True,
        "seeded_groups": seeded,
        "source_relationship_id": relationship_id,
        "source_relationship_name": relationship.get("displayName", ""),
    }
