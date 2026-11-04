"""
Shared HaloPSA Project Tools

Reusable, LLM-friendly project operations for any Bifrost agent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bifrost import tool, UserError
from modules.extensions.halopsa import classify_halo_project
from modules.extensions.halopsa import create_project as ext_create_project
from modules.extensions.halopsa import delete_project as ext_delete_project
from modules.extensions.halopsa import get_project as ext_get_project
from modules.extensions.halopsa import list_project_children as ext_list_project_children
from modules.extensions.halopsa import list_projects as ext_list_projects
from modules.extensions.halopsa import get_project_client_id
from modules.extensions.halopsa import summarize_halo_project
from modules.extensions.halopsa import update_project as ext_update_project

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

_PROJECT_WRITEABLE_FIELDS: set[str] = {
    "summary",
    "details",
    "client_id",
    "site_id",
    "parent_id",
    "team_id",
    "agent_id",
    "tickettype_id",
    "status_id",
    "workflow_id",
    "workflow_stage_id",
    "milestone_id",
    "start_date",
    "target_date",
    "contract_id",
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


def _parse_halo_datetime(value: str | None) -> datetime | None:
    """Parse Halo date-ish strings into UTC-aware datetimes when possible."""
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    for candidate in (text, f"{text}T00:00:00"):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    return None


def _days_between(start: datetime | None, end: datetime | None) -> int | None:
    """Return whole-day distance between two datetimes when both are present."""
    if start is None or end is None:
        return None
    return (end - start).days


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


def _declared_scope(project: dict) -> dict[str, list[str]]:
    """Return the normalized declared-scope buckets from custom fields."""
    field_map = _custom_field_label_map(project)
    return {
        "modules": field_map.get("CFOnboardingModules", []),
        "integrations": field_map.get("CFIntegrations", []),
        "migration_scope": field_map.get("CFOnboardingMigration", []),
    }


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
    scope = _declared_scope(project)
    module_labels = scope["modules"]
    integration_labels = scope["integrations"]
    migration_labels = scope["migration_scope"]

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
        "declared_scope": _declared_scope(project_detail),
        "execution_structure": {
            "child_count": len(child_summaries),
            "project_kind_distribution": dict(sorted(kind_counts.items())),
            "children": child_summaries,
        },
        "drift_summary": _build_execution_drift(project_detail, child_summaries),
    }


def build_canonical_project_model(project: dict, children: list[dict]) -> dict:
    """Build the stable Bifrost-facing project model for read and planning workflows."""
    project_detail = _project_detail(project)
    child_summaries = [summarize_halo_project(child) for child in children]
    declared_scope = _declared_scope(project_detail)
    execution_coverage = _build_execution_drift(project_detail, child_summaries)

    project_start = _parse_halo_datetime(project_detail.get("start_date"))
    project_target = _parse_halo_datetime(project_detail.get("target_date"))

    structure_items = []
    for child in child_summaries:
        child_start = _parse_halo_datetime(child.get("start_date"))
        child_target = _parse_halo_datetime(child.get("target_date"))
        structure_items.append(
            {
                "id": child.get("id"),
                "parent_id": child.get("parent_id"),
                "summary": child.get("summary", ""),
                "project_kind": child.get("project_kind"),
                "project_kind_confidence": child.get("project_kind_confidence"),
                "status": child.get("status", ""),
                "team": child.get("team", ""),
                "agent_name": child.get("agent_name", ""),
                "start_date": child.get("start_date", ""),
                "target_date": child.get("target_date", ""),
                "duration_days": _days_between(child_start, child_target),
                "has_schedule": bool(child_start or child_target),
                "has_status": bool(child.get("status")),
                "child_count": child.get("child_count"),
            }
        )

    return {
        "project_core": {
            "id": project_detail.get("id"),
            "summary": project_detail.get("summary", ""),
            "details": project_detail.get("details", ""),
            "status": project_detail.get("status", ""),
            "status_id": project_detail.get("status_id"),
            "client_id": project_detail.get("client_id"),
            "client": project_detail.get("client", ""),
            "site_id": project_detail.get("site_id"),
            "site_name": project_detail.get("site_name", ""),
            "tickettype_id": project_detail.get("tickettype_id"),
            "tickettype_name": project_detail.get("tickettype_name", ""),
            "team_id": project_detail.get("team_id"),
            "team": project_detail.get("team", ""),
            "agent_id": project_detail.get("agent_id"),
            "agent_name": project_detail.get("agent_name", ""),
            "workflow_id": project_detail.get("workflow_id"),
            "workflow_name": project_detail.get("workflow_name", ""),
            "workflow_stage_id": project_detail.get("workflow_stage_id"),
            "workflow_stage": project_detail.get("workflow_stage", ""),
            "start_date": project_detail.get("start_date", ""),
            "target_date": project_detail.get("target_date", ""),
            "duration_days": _days_between(project_start, project_target),
            "project_kind": project_detail.get("project_kind"),
            "project_kind_confidence": project_detail.get("project_kind_confidence"),
            "project_completion_percentage": project_detail.get("project_completion_percentage"),
            "project_time_percentage": project_detail.get("project_time_percentage"),
            "project_time_budget": project_detail.get("project_time_budget"),
            "project_time_actual": project_detail.get("project_time_actual"),
            "project_money_budget": project_detail.get("project_money_budget"),
            "project_money_actual": project_detail.get("project_money_actual"),
            "budgettype_id": project_detail.get("budgettype_id"),
            "budgettype_name": project_detail.get("budgettype_name", ""),
            "contract_id": project_detail.get("contract_id"),
            "contract_ref": project_detail.get("contract_ref"),
            "inactive": project_detail.get("inactive"),
        },
        "project_structure": {
            "child_count": len(structure_items),
            "child_count_open": project_detail.get("child_count_open"),
            "items": structure_items,
        },
        "declared_scope": declared_scope,
        "execution_coverage": execution_coverage,
    }


def build_project_timeline_model(project: dict, children: list[dict]) -> dict:
    """Build a timeline/Gantt-friendly read model for a HaloPSA project."""
    canonical = build_canonical_project_model(project, children)
    core = canonical["project_core"]
    structure = canonical["project_structure"]
    all_items = [
        {
            "id": core["id"],
            "parent_id": None,
            "summary": core["summary"],
            "project_kind": core["project_kind"],
            "status": core["status"],
            "team": core["team"],
            "agent_name": core["agent_name"],
            "start_date": core["start_date"],
            "target_date": core["target_date"],
            "duration_days": core["duration_days"],
            "has_schedule": bool(core["start_date"] or core["target_date"]),
            "is_parent": True,
        }
    ]

    for item in structure["items"]:
        timeline_item = dict(item)
        timeline_item["is_parent"] = False
        all_items.append(timeline_item)

    unscheduled_count = sum(1 for item in all_items if not item.get("has_schedule"))
    scheduled_items = [item for item in all_items if item.get("has_schedule")]

    return {
        "project_id": core["id"],
        "project_summary": core["summary"],
        "timeline": all_items,
        "summary": {
            "item_count": len(all_items),
            "scheduled_item_count": len(scheduled_items),
            "unscheduled_item_count": unscheduled_count,
            "project_start_date": core["start_date"],
            "project_target_date": core["target_date"],
        },
    }


def build_project_health_summary(project: dict, children: list[dict]) -> dict:
    """Build a pragmatic health summary focused on project-management usability."""
    canonical = build_canonical_project_model(project, children)
    core = canonical["project_core"]
    structure = canonical["project_structure"]
    coverage = canonical["execution_coverage"]

    items = structure["items"]
    missing_status_count = sum(1 for item in items if not item.get("status"))
    unscheduled_count = sum(1 for item in items if not item.get("has_schedule"))
    milestone_count = sum(1 for item in items if item.get("project_kind") == "subproject")

    scope_gaps = sum(
        len((coverage.get(category_name) or {}).get("missing_from_child_workstreams") or [])
        for category_name in (
            "declared_modules",
            "declared_integrations",
            "declared_migration_scope",
        )
    )

    concerns = []
    if missing_status_count:
        concerns.append(
            f"{missing_status_count} child items have no usable status text."
        )
    if unscheduled_count:
        concerns.append(
            f"{unscheduled_count} child items have no schedule dates."
        )
    if scope_gaps:
        concerns.append(
            f"{scope_gaps} declared scope items are not backed by current child workstreams."
        )
    if milestone_count == 0:
        concerns.append("No milestone-like child records are currently identified.")

    score = 100
    score -= min(missing_status_count * 2, 30)
    score -= min(unscheduled_count * 2, 30)
    score -= min(scope_gaps * 5, 25)
    if milestone_count == 0:
        score -= 10
    score = max(score, 0)

    if score >= 85:
        health = "strong"
    elif score >= 65:
        health = "usable"
    elif score >= 40:
        health = "fragile"
    else:
        health = "weak"

    return {
        "project_id": core["id"],
        "project_summary": core["summary"],
        "health": health,
        "score": score,
        "signals": {
            "child_count": structure["child_count"],
            "unscheduled_child_count": unscheduled_count,
            "children_missing_status_count": missing_status_count,
            "scope_gap_count": scope_gaps,
            "subproject_count": milestone_count,
        },
        "concerns": concerns,
        "execution_coverage": coverage,
    }


def _validated_project_fields(fields: dict, *, require_client: bool = False) -> dict:
    """Filter and validate mutable project fields for safe write operations."""
    if not fields:
        raise UserError("No fields provided.")

    invalid = sorted(key for key in fields if key not in _PROJECT_WRITEABLE_FIELDS)
    if invalid:
        raise UserError(
            "Unsupported project fields: "
            + ", ".join(invalid)
            + ". Use the normalized project field names exposed by Bifrost."
        )

    summary = fields.get("summary")
    if summary is not None and not str(summary).strip():
        raise UserError("Project summary cannot be blank.")
    if require_client and not fields.get("client_id"):
        raise UserError("client_id is required for provider users when creating a project.")

    return dict(fields)


async def _get_accessible_project(project_id: int) -> dict:
    """Fetch a project and enforce caller access in one step."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    return project


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


@tool(description="Return the canonical Bifrost project model for a HaloPSA project, including core metadata, structure, declared scope, and execution coverage.")
async def get_project_model(project_id: int, include_inactive: bool = False) -> dict:
    """Fetch a HaloPSA project as Bifrost's canonical project model."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    children = await ext_list_project_children(project_id, include_inactive=include_inactive)
    for child in children:
        await _check_project_access(child)
    return build_canonical_project_model(project, children)


@tool(description="Return a HaloPSA project in a timeline-friendly shape for future Gantt and scheduling interfaces.")
async def get_project_timeline(project_id: int, include_inactive: bool = False) -> dict:
    """Fetch a HaloPSA project timeline model."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    children = await ext_list_project_children(project_id, include_inactive=include_inactive)
    for child in children:
        await _check_project_access(child)
    return build_project_timeline_model(project, children)


@tool(description="Summarize the practical health of a HaloPSA project, focusing on schedule coverage, child statuses, and scope drift.")
async def summarize_project_health(project_id: int, include_inactive: bool = False) -> dict:
    """Summarize health signals for a HaloPSA project."""
    project = await ext_get_project(project_id)
    await _check_project_access(project)
    children = await ext_list_project_children(project_id, include_inactive=include_inactive)
    for child in children:
        await _check_project_access(child)
    return build_project_health_summary(project, children)


@tool(description="Create a HaloPSA project or child project record using normalized Bifrost field names.")
async def create_project(
    summary: str,
    client_id: int | None = None,
    details: str = "",
    site_id: int | None = None,
    parent_id: int | None = None,
    team_id: int | None = None,
    agent_id: int | None = None,
    tickettype_id: int | None = None,
    start_date: str = "",
    target_date: str = "",
) -> dict:
    """Create a HaloPSA project with a narrow, safe field surface."""
    scope = get_caller_scope()
    if not summary.strip():
        raise UserError("Project summary is required.")

    effective_client_id = client_id
    if not scope["is_provider"]:
        if not scope["org_id"]:
            raise UserError("No organization context is available for this request.")
        effective_client_id = await resolve_client_id(scope["org_id"])
    elif effective_client_id is None:
        raise UserError("client_id is required for provider users.")

    fields = _validated_project_fields(
        {
            "summary": summary.strip(),
            "details": details.strip(),
            "client_id": effective_client_id,
            "site_id": site_id,
            "parent_id": parent_id,
            "team_id": team_id,
            "agent_id": agent_id,
            "tickettype_id": tickettype_id,
            "start_date": start_date.strip(),
            "target_date": target_date.strip(),
        },
        require_client=True,
    )
    created = await ext_create_project(fields)
    await _check_project_access(created)
    return _project_detail(created)


@tool(description="Update fields on an existing HaloPSA project using normalized Bifrost field names.")
async def update_project(project_id: int, fields: dict) -> dict:
    """Update a HaloPSA project with a constrained, normalized field set."""
    existing = await ext_get_project(project_id)
    await _check_project_access(existing)
    validated = _validated_project_fields(fields)

    if "client_id" in validated:
        allowed_client_id = await _get_scoped_client_id()
        if allowed_client_id is not None and validated["client_id"] != allowed_client_id:
            raise UserError("You can't move this project to a different Halo client.")

    updated = await ext_update_project(project_id, validated)
    await _check_project_access(updated)
    return _project_detail(updated)


@tool(description="Update the assigned HaloPSA team and/or agent for a project or child work item.")
async def update_project_owner(
    project_id: int,
    team_id: int | None = None,
    agent_id: int | None = None,
) -> dict:
    """Update project ownership using the safe normalized write surface."""
    if team_id is None and agent_id is None:
        raise UserError("Provide at least one of team_id or agent_id.")

    fields = {}
    if team_id is not None:
        fields["team_id"] = team_id
    if agent_id is not None:
        fields["agent_id"] = agent_id
    return await update_project(project_id, fields)


@tool(description="Rename a HaloPSA project or child work item by setting its summary.")
async def rename_project_item(project_id: int, summary: str) -> dict:
    """Rename a HaloPSA project record."""
    if not summary.strip():
        raise UserError("Project summary cannot be blank.")
    return await update_project(project_id, {"summary": summary.strip()})


@tool(description="Update the planned start and target dates for a HaloPSA project or child work item.")
async def update_project_dates(project_id: int, start_date: str = "", target_date: str = "") -> dict:
    """Update project schedule dates using normalized field names."""
    if not start_date.strip() and not target_date.strip():
        raise UserError("Provide at least one of start_date or target_date.")

    fields = {}
    if start_date.strip():
        fields["start_date"] = start_date.strip()
    if target_date.strip():
        fields["target_date"] = target_date.strip()
    return await update_project(project_id, fields)


@tool(description="Create a child workstream under an existing HaloPSA project, inheriting client and site defaults from the parent.")
async def create_project_workstream(
    parent_project_id: int,
    summary: str,
    details: str = "",
    site_id: int | None = None,
    team_id: int | None = None,
    agent_id: int | None = None,
    tickettype_id: int | None = None,
    start_date: str = "",
    target_date: str = "",
) -> dict:
    """Create a child project/workstream with parent-derived defaults."""
    if not summary.strip():
        raise UserError("Workstream summary is required.")

    parent = await _get_accessible_project(parent_project_id)

    created = await ext_create_project(
        _validated_project_fields(
            {
                "summary": summary.strip(),
                "details": details.strip(),
                "client_id": parent.get("client_id"),
                "site_id": site_id if site_id is not None else parent.get("site_id"),
                "parent_id": parent_project_id,
                "team_id": team_id if team_id is not None else parent.get("team_id"),
                "agent_id": agent_id if agent_id is not None else parent.get("agent_id"),
                "tickettype_id": tickettype_id if tickettype_id is not None else parent.get("tickettype_id"),
                "start_date": start_date.strip(),
                "target_date": target_date.strip(),
            },
            require_client=True,
        )
    )
    await _check_project_access(created)
    return {
        "parent_project_id": parent_project_id,
        "parent_project_summary": parent.get("summary", ""),
        "workstream": _project_detail(created),
    }


@tool(description="Delete a HaloPSA project or child work item. Set confirm=true to proceed.")
async def delete_project(project_id: int, confirm: bool = False) -> dict:
    """Delete a HaloPSA project only when explicitly confirmed."""
    if not confirm:
        raise UserError("Refusing to delete the project without confirm=true.")

    existing = await ext_get_project(project_id)
    await _check_project_access(existing)
    await ext_delete_project(project_id)
    return {
        "deleted": True,
        "project_id": project_id,
        "project_summary": existing.get("summary", ""),
    }
