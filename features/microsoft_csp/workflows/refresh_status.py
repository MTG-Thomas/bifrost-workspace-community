"""
Refresh CSP Tenant Status

Alias for consent_csp_tenant - both initial consent and refresh use the same flow.
"""

from bifrost import workflow
from modules.extensions.platform_auth import require_platform_admin

from features.microsoft_csp.workflows.consent_tenant import consent_csp_tenant


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "consent", "refresh"],
)
async def refresh_csp_status(tenant_id: str) -> dict:
    """
    Refresh/reconsent a tenant to ensure all permissions are up-to-date.
    
    This is an alias for consent_csp_tenant - the same flow handles both
    initial consent and refresh.

    Args:
        tenant_id: Customer's Entra tenant ID

    Returns:
        Consent result with details
    """
    require_platform_admin()
    return await consent_csp_tenant(tenant_id)
