"""
Authorization helpers for shared HaloPSA tools.

Provides caller scoping (provider vs org user) and ticket access checks.
"""

from bifrost import context, UserError


def normalize_record(value: object) -> dict:
    """Normalize a Halo SDK dict/DotDict, failing closed for absent records."""
    return value if isinstance(value, dict) else dict(value) if value else {}


async def check_client_target(client_id: object) -> None:
    """Bind a caller-selected Halo client to the caller's mapped organization."""
    if (
        getattr(context, "user_id", None)
        and getattr(context, "is_platform_admin", False) is True
        and not getattr(context, "is_function_key", False)
    ):
        return
    if client_id is None:
        organization = getattr(context, "organization", None)
        if (
            getattr(context, "user_id", None)
            and not getattr(context, "is_function_key", False)
            and getattr(organization, "is_provider", False) is True
        ):
            return
        raise UserError("Provider time entry access denied.")
    org_id = getattr(context, "org_id", None)
    if not org_id:
        raise UserError("Client access could not be verified.")
    from modules.extensions.halopsa import resolve_client_id

    allowed_client_id = await resolve_client_id(org_id)
    if str(client_id) != str(allowed_client_id):
        raise UserError("Client access denied.")


def check_appointment_owner(appointment: dict, agent_id: object) -> None:
    assigned = appointment.get("agents") or []
    if not any(str(normalize_record(member).get("id")) == str(agent_id) for member in assigned):
        raise UserError("Appointment access denied.")


def check_action_owner(action: dict, agent_id: object, ticket_id: object) -> None:
    if (
        str(action.get("who_agentid")) != str(agent_id)
        or str(action.get("ticket_id")) != str(ticket_id)
    ):
        raise UserError("Action access denied.")


def check_ticket_email_target(ticket: dict, agent_id: object, recipient: str) -> None:
    """Allow a ticket email only by its assigned agent to its recorded requester."""
    if (
        str(ticket.get("agent_id")) != str(agent_id)
        or not ticket.get("user_email")
        or ticket["user_email"].strip().casefold() != recipient.strip().casefold()
    ):
        raise UserError("Ticket email target access denied.")


def get_caller_scope() -> dict:
    """Return caller identity for authorization decisions.

    Missing organization or caller identity never confers provider access.
    """
    org = getattr(context, "organization", None)
    identified = bool(getattr(context, "user_id", None)) and not getattr(context, "is_function_key", False)
    is_provider = identified and (
        getattr(context, "is_platform_admin", False) is True
        or getattr(org, "is_provider", False) is True
    )
    org_id = getattr(context, "org_id", None)
    if not identified or (not is_provider and not org_id):
        raise UserError("Caller scope could not be verified.")
    return {
        "identified": identified,
        "is_provider": is_provider,
        "email": getattr(context, "email", None),
        "org_id": org_id,
    }


async def check_ticket_access(ticket: dict) -> None:
    """Raise UserError if an org user tries to access a ticket they don't own.

    Provider users have unrestricted access.
    Org users can only access tickets where they are the requestor (matched by email).
    """
    scope = get_caller_scope()
    if scope["is_provider"]:
        return

    ticket_email = (
        ticket.get("user_emailaddress") or ticket.get("useremail") or ""
    ).lower()
    caller_email = (scope["email"] or "").lower()

    if not caller_email or ticket_email != caller_email:
        raise UserError("You don't have access to this ticket.")
