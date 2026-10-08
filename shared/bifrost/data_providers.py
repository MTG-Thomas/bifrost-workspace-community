"""
Bifrost Data Providers

Data providers for Bifrost-related form dropdowns.
"""

import logging

from bifrost import data_provider, organizations
from modules.extensions.platform_auth import require_platform_admin

logger = logging.getLogger(__name__)


@data_provider(
    name="bifrost_organizations",
    description="List all Bifrost organizations",
    category="Bifrost",
)
async def bifrost_organizations() -> list[dict]:
    """
    Return list of Bifrost organizations for dropdown selection.

    Returns:
        List of options with org_id as value and org name as label.
    """
    require_platform_admin()
    logger.debug("Fetching Bifrost organizations for data provider")

    orgs = await organizations.list()

    options = []
    for org in orgs:
        org_id = org.id
        org_name = org.name

        if not org_id or not org_name:
            continue

        options.append({
            "label": org_name,
            "value": org_id,
            "metadata": {
                "created_at": getattr(org, "created_at", None),
            },
        })

    # Sort alphabetically by org name
    options.sort(key=lambda x: x["label"].lower())

    logger.debug(f"Returning {len(options)} Bifrost organizations")
    return options
