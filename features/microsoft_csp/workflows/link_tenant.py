"""
Link CSP Tenant to Bifrost Organization

Links a Microsoft CSP tenant to a Bifrost organization,
enabling Graph API and other Microsoft integrations for that org.
"""

import logging
from datetime import datetime, timezone

from bifrost import workflow, tables, config, context, integrations, organizations, UserError
from modules.extensions.platform_auth import require_platform_admin

logger = logging.getLogger(__name__)

STATUS_TABLE = "csp_tenant_status"


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "link"],
)
async def link_csp_tenant(
    tenant_id: str,
    tenant_name: str,
    domain: str,
    customer_id: str,
    org_id: str | None,
    org_name: str | None,
) -> dict:
    """
    Link a CSP tenant to a Bifrost organization.

    This stores the mapping in the status table and also sets
    the entra_tenant_id config on the organization for Graph API access.

    Args:
        tenant_id: Microsoft Entra tenant ID
        tenant_name: Company name from Partner Center
        domain: Primary domain
        customer_id: Partner Center customer ID
        org_id: Bifrost organization ID to link (None to unlink)
        org_name: Organization name for display

    Returns:
        Updated tenant status
    """
    require_platform_admin()
    if not tenant_id:
        raise UserError("tenant_id is required")

    if org_id:
        # The page's identifiers and names are hints, not proof of a CSP link.
        from modules.microsoft import create_csp_client

        csp = await create_csp_client()
        customer = csp.get_customer(tenant_id)
        profile = customer.get("companyProfile") or {}
        if (
            str(profile.get("tenantId", "")).casefold() != tenant_id.casefold()
            or str(customer.get("id", "")).casefold() != customer_id.casefold()
        ):
            raise UserError("Tenant and customer identity could not be verified in Partner Center.")
        target_org = await organizations.get(org_id)
        if target_org.id != org_id or not target_org.is_active:
            raise UserError("Target organization is not active or could not be verified.")
        tenant_name = profile.get("companyName") or tenant_name
        domain = profile.get("domain") or domain
        org_name = target_org.name

    # Get provider org ID from context
    provider_org_id = context.org_id

    logger.info(
        "Linking CSP tenant",
        extra={
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "org_id": org_id,
        }
    )

    # Get existing status to preserve consent info (table may not exist yet)
    try:
        existing = await tables.get(STATUS_TABLE, tenant_id, scope=provider_org_id)
        existing_data = existing.data if existing else {}
    except Exception as error:
        if org_id is None:
            raise UserError("Existing tenant link could not be verified.") from error
        existing_data = {}

    if org_id:
        prior_org_id = existing_data.get("bifrost_org_id")
        existing_mappings = await integrations.list_mappings("Microsoft", scope="global") or []
        if any(
            str(mapping.entity_id).casefold() == tenant_id.casefold()
            and mapping.organization_id not in (org_id, prior_org_id)
            for mapping in existing_mappings
        ):
            raise UserError("Microsoft tenant is already linked to another organization.")

    # Build updated status
    now = datetime.now(timezone.utc).isoformat()
    status_data = {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "domain": domain,
        "customer_id": customer_id,
        "bifrost_org_id": org_id,
        "bifrost_org_name": org_name,
        # Preserve consent status
        "consent_status": existing_data.get("consent_status", "none"),
        "consent_error": existing_data.get("consent_error"),
        "consented_at": existing_data.get("consented_at"),
        "updated_at": now,
    }

    if org_id:
        current_mapping = await integrations.get_mapping("Microsoft", scope=org_id)
        if current_mapping and current_mapping.entity_id not in (None, tenant_id):
            raise UserError("Organization is already linked to another Microsoft tenant.")

    previous_org_id = existing_data.get("bifrost_org_id")
    if previous_org_id and previous_org_id != org_id:
        # Remove only values that still point to this tenant. Another link may
        # have replaced one of them since the status row was written.
        previous_mapping = await integrations.get_mapping("Microsoft", scope=previous_org_id)
        if previous_mapping and previous_mapping.entity_id == tenant_id:
            await integrations.delete_mapping("Microsoft", scope=previous_org_id)
        previous_config = await config.get("entra_tenant_id", scope=previous_org_id)
        if previous_config == tenant_id:
            await config.delete("entra_tenant_id", scope=previous_org_id)

    # If linking to an org, set up Microsoft integration mapping
    if org_id:
        # Set entra_tenant_id config (legacy, for backwards compatibility)
        await config.set("entra_tenant_id", tenant_id, scope=org_id)

        # Create IntegrationMapping for Microsoft integration
        # This enables integrations.get("Microsoft") to resolve the tenant_id
        # and fetch a fresh token for client credentials access
        await integrations.upsert_mapping(
            "Microsoft",
            scope=org_id,
            entity_id=tenant_id,
            entity_name=tenant_name or domain or tenant_id,
        )

        logger.info(
            "Linked CSP tenant to organization",
            extra={"org_id": org_id, "tenant_id": tenant_id}
        )

    # A failed cleanup or mapping write must not make the status claim success.
    await tables.upsert(STATUS_TABLE, id=tenant_id, data=status_data, scope=provider_org_id)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "bifrost_org_id": org_id,
        "bifrost_org_name": org_name,
        "consent_status": status_data["consent_status"],
    }
