"""
Shared HaloPSA Project Tools

Reusable, LLM-friendly project operations for any Bifrost agent.
"""

from __future__ import annotations

from bifrost import tool, UserError
from modules.extensions.halopsa import classify_halo_project
from modules.extensions.halopsa import get_project as ext_get_project
from modules.extensions.halopsa import list_project_children as ext_list_project_children
from modules.extensions.halopsa import list_projects as ext_list_projects
from modules.extensions.halopsa import get_project_client_id
from modules.extensions.halopsa import summarize_halo_project

from shared.halopsa.tools._auth import get_caller_scope
from modules.extensions.halopsa import resolve_client_id


_MODULE_WORKSTREAM_ALIASES: dict[str, set[str]] = {
    "service desk": {
        "service catalogue",
        "ticket types",
        "categories",
        "slas",
        "statuses",
        "actions and workflows",
        "approval processes",
        "notifications",
        "mailbox configuration",
        "email templates",
        "closure procedures and feedback",
    },
    "self service portal": {
        "self service portal branding and customisation",
        "service catalogue",
    },
    "billing": {
        "billing rules",
        "recurring invoices",
        "charge rates",
        "tax rates",
        "contracts agreements",
    },
    "sales crm": {
        "quotations",
        "sales orders",
        "opportunity types and workflow",
    },
    "assets rmm": {
        "import items",
        "item groups",
        "item bundles",
        "stock",
        "vendors suppliers",
    },
    "reporting and dashboards": {"reporting and dashboards"},
    "core configuration": {
        "organization setup",
        "general navigation areas and views",
        "time management and calendars appointments",
    },
    "knowledge base": {"knowledge base"},
    "projects": {"projects"},
}

_CATEGORY_UMBRELLA_CHILDREN: dict[str, set[str]] = {
    "declared_integrations": {"integrations"},
    "declared_migration_scope": {"data migration imports"},
}


async def _get_scoped_client_id() -> int | None:
    """Return the caller's allowed client ID, or None for provider users."""
    scope = get_caller_scope()
    if scope["is_provider"]:
        return None
    if not scope["org_id"]:
        raise UserError("No organization context is available for this request.")
    return await resolve_client_id(scope["org_id"])


async def _check_project_access(project: dict) -> None:
    """Raise if an org user tries to access a project outside their Halo client."""
    allowed_client_id = await _get_scoped_client_id()
    if allowed_client_id is None:
        return

    project_client_id = get_project_client_id(project)
    if project_client_id is None:
        raise UserError("This HaloPSA project is missing a client association.")
    if project_client_id != allowed_client_id:
        raise UserError("You don't have access to this HaloPSA project.")


def _project_detail(project: dict) -> dict:
    """Render the richer normalized project detail shape."""
    classification = classify_halo_project(project)
    return {
        "id": project.get("id"),
        "summary": project.get("summary", ""),
        "details": project.get("details", ""),
        "status": project.get("status", ""),
        "status_id": project.get("status_id"),
        "client_id": project.get("client_id"),
        "client": project.get("client_name", ""),
        "site_id": project.get("site_id"),
        "site_name": project.get("site_name", ""),
        "tickettype_id": project.get("tickettype_id"),
        "tickettype_name": project.get("tickettype_name", ""),
        "team_id": project.get("team_id"),
        "team": project.get("team", ""),
        "agent_id": project.get("agent_id"),
        "agent_name": project.get("agent_name", ""),
        "start_date": project.get("start_date", ""),
        "target_date": project.get("target_date", ""),
        "date_opened": project.get("date_opened", ""),
        "date_closed": project.get("date_closed", ""),
        "parent_id": project.get("parent_id"),
        "child_count": project.get("child_count"),
        "child_count_open": project.get("child_count_open"),
        "milestone_id": project.get("milestone_id"),
        "milestone_name": project.get("milestone_name", ""),
        "workflow_id": project.get("workflow_id"),
        "workflow_name": project.get("workflow_name", ""),
        "workflow_stage": project.get("workflow_stage", ""),
        "workflow_stage_id": project.get("workflow_stage_id"),
        "project_completion_percentage": project.get("project_completion_percentage"),
        "project_time_percentage": project.get("project_time_percentage"),
        "project_time_budget": project.get("project_time_budget"),
        "project_time_actual": project.get("project_time_actual"),
        "project_money_budget": project.get("project_money_budget"),
        "project_money_actual": project.get("project_money_actual"),
        "budgettype": project.get("budgettype"),
        "budgettype_id": project.get("budgettype_id"),
        "budgettype_name": project.get("budgettype_name", ""),
        "contract_id": project.get("contract_id"),
        "contract_ref": project.get("contract_ref"),
        "has_been_closed": project.get("has_been_closed"),
        "appointment_count": project.get("appointment_count"),
        "task_count": project.get("task_count"),
        "quotation_count": project.get("quotation_count"),
        "salesorder_count": project.get("salesorder_count"),
        "purchaseorder_count": project.get("purchaseorder_count"),
        "invoice_line_count": project.get("invoice_line_count"),
        "custom_fields_count": project.get("custom_fields_count"),
        "custom_fields": project.get("custom_fields", []),
        "attachments_count": project.get("attachments_count"),
        "documents_count": project.get("documents_count"),
        "timeentries_count": project.get("timeentries_count"),
        "budgets_count": project.get("budgets_count"),
        "is_project": project.get("is_project"),
        "inactive": project.get("inactive"),
        "project_kind": project.get("project_kind") or classification["project_kind"],
        "project_kind_confidence": project.get("project_kind_confidence") or classification["project_kind_confidence"],
        "project_kind_reason": project.get("project_kind_reason") or classification["project_kind_reason"],
    }


def _extract_multiselect_labels(value) -> list[str]:
    """Normalize Halo multi-select custom field values to a flat label list."""
    if not isinstance(value, list):
        return []

    labels = []
    for item in value:
        if isinstance(item, dict):
            label = item.get("label") or item.get("name") or item.get("value")
        else:
            label = item
        if label in (None, ""):
            continue
        labels.append(str(label).strip())
    return labels


def _custom_field_label_map(project: dict) -> dict[str, list[str]]:
    """Map custom field labels to normalized value labels."""
    result = {}
    for field in project.get("custom_fields", []):
        label = str(field.get("label") or "").strip()
        if not label:
            continue
        values = _extract_multiselect_labels(field.get("value"))
        if values:
            result[label] = values
    return result


def _normalize_execution_name(name: str) -> str:
    """Normalize a child summary for rough drift matching."""
    return " ".join(str(name or "").lower().replace("&", " and ").replace("/", " ").split())


def _find_matching_workstreams(
    label: str,
    child_name_map: dict[str, str],
    *,
    category_key: str,
) -> list[str]:
    """Return child workstream names that substantively back a declared scope label."""
    normalized_label = _normalize_execution_name(label)
    alias_candidates = {normalized_label}

    if category_key == "declared_modules":
        alias_candidates.update(_MODULE_WORKSTREAM_ALIASES.get(normalized_label, set()))

    matches: list[str] = []
    for normalized_child_name, original_child_name in child_name_map.items():
        if normalized_child_name in _CATEGORY_UMBRELLA_CHILDREN.get(category_key, set()):
            matches.append(original_child_name)
            continue
        if any(
            candidate and (
                candidate in normalized_child_name
                or normalized_child_name in candidate
            )
            for candidate in alias_candidates
            if normalized_child_name
        ):
            matches.append(original_child_name)

    # Preserve order but remove duplicates.
    return list(dict.fromkeys(matches))


def _build_execution_drift(project: dict, children: list[dict]) -> dict:
    """Compare declared parent scope against the current child workstream structure."""
    field_map = _custom_field_label_map(project)
    module_labels = field_map.get("CFOnboardingModules", [])
    integration_labels = field_map.get("CFIntegrations", [])
    migration_labels = field_map.get("CFOnboardingMigration", [])

    child_name_map = {
        _normalize_execution_name(child.get("summary", "")): child.get("summary", "")
        for child in children
        if child.get("summary")
    }

    def _coverage(labels: list[str], *, category_key: str) -> dict:
        backed = []
        missing = []
        match_details = []
        for label in labels:
            matched_children = _find_matching_workstreams(
                label,
                child_name_map,
                category_key=category_key,
            )
            if matched_children:
                backed.append(label)
            else:
                missing.append(label)
            match_details.append(
                {
                    "declared_item": label,
                    "matched_workstreams": matched_children,
                }
            )
        return {
            "declared": labels,
            "backed_by_child_workstreams": backed,
            "missing_from_child_workstreams": missing,
            "match_details": match_details,
        }

    return {
        "declared_modules": _coverage(module_labels, category_key="declared_modules"),
        "declared_integrations": _coverage(integration_labels, category_key="declared_integrations"),
        "declared_migration_scope": _coverage(migration_labels, category_key="declared_migration_scope"),
    }


def summarize_project_execution_context(project: dict, children: list[dict]) -> dict:
    """Build reusable execution context and drift summary from a parent and children."""
    project_detail = _project_detail(project)
    child_summaries = [summarize_halo_project(child) for child in children]
    kind_counts: dict[str, int] = {}
    for child in child_summaries:
        kind = child.get("project_kind") or "unknown"
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    return {
        "project": project_detail,
        "declared_scope": _custom_field_label_map(project_detail),
        "execution_structure": {
            "child_count": len(child_summaries),
            "project_kind_distribution": dict(sorted(kind_counts.items())),
            "children": child_summaries,
        },
        "drift_summary": _build_execution_drift(project_detail, child_summaries),
    }


@tool(description="List HaloPSA projects. Org users only see projects for their linked Halo client.")
async def list_projects(
    search: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 10,
    client_id: int | None = None,
    include_inactive: bool = False,
) -> dict:
    """List HaloPSA projects with optional search and status filtering."""
    page = max(page, 1)
    page_size = max(1, min(page_size, 25))

    allowed_client_id = await _get_scoped_client_id()
    effective_client_id = allowed_client_id if allowed_client_id is not None else client_id

    projects = await ext_list_projects(
        client_id=effective_client_id,
        include_inactive=include_inactive,
    )

    if search:
        search_lower = search.lower()
        projects = [
            project
            for project in projects
            if search_lower in (project.get("summary") or "").lower()
            or search_lower in (project.get("client_name") or "").lower()
            or search_lower in str(project.get("id") or "")
        ]

    if status:
        status_lower = status.lower()
        projects = [
            project
            for project in projects
            if (project.get("status") or "").lower() == status_lower
        ]

    total = len(projects)
    start = (page - 1) * page_size
    end = start + page_size
    page_projects = projects[start:end]

    return {
        "projects": [
            summarize_halo_project(project)
            for project in page_projects
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@tool(description="Get a HaloPSA project by ID with status, client, timeline, and budget details.")
async def get_project(project_id: int) -> dict:
    """Fetch a single HaloPSA project and enforce org scoping."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    return _project_detail(project)


@tool(description="List child records for a HaloPSA project, including workstreams and sub-tasks.")
async def list_project_children(project_id: int, include_inactive: bool = False) -> dict:
    """Fetch child records for a HaloPSA project and enforce org scoping."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    children = await ext_list_project_children(project_id, include_inactive=include_inactive)
    for child in children:
        await _check_project_access(child)

    return {
        "project_id": project_id,
        "project_summary": project.get("summary", ""),
        "children": [summarize_halo_project(child) for child in children],
        "count": len(children),
    }


@tool(description="Get a HaloPSA project together with its child records in one response.")
async def get_project_tree(project_id: int, include_inactive: bool = False) -> dict:
    """Fetch a HaloPSA project tree and enforce org scoping."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    children = await ext_list_project_children(project_id, include_inactive=include_inactive)
    for child in children:
        await _check_project_access(child)

    return {
        "project": _project_detail(project),
        "children": [summarize_halo_project(child) for child in children],
        "count": len(children),
    }


@tool(description="Summarize a HaloPSA project's declared scope, execution structure, and basic drift between parent metadata and child workstreams.")
async def summarize_project_execution(project_id: int, include_inactive: bool = False) -> dict:
    """Summarize execution context for a HaloPSA project."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    children = await ext_list_project_children(project_id, include_inactive=include_inactive)
    for child in children:
        await _check_project_access(child)

    return summarize_project_execution_context(project, children)
