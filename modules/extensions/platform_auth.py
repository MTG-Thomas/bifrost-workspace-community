"""Authorization guard for provider-wide workflow and agent tool operations."""

from bifrost import UserError, context


def require_platform_admin() -> None:
    """Require a trusted platform-admin execution with an identified user.

    An absent organization is a scope value, never evidence of privilege.
    Function-key invocations are not interactive platform administrators.
    """
    if (
        not getattr(context, "user_id", None)
        or getattr(context, "is_platform_admin", False) is not True
        or getattr(context, "is_function_key", False)
    ):
        raise UserError("Platform administrator access is required.")


def require_org_access(requested_org_id: str = "") -> str:
    """Return an authorized org before a caller-selected scope is applied."""
    if not getattr(context, "user_id", None) or getattr(context, "is_function_key", False):
        raise UserError("Organization access could not be verified.")
    current_org_id = getattr(context, "org_id", None)
    effective_org_id = requested_org_id or current_org_id
    if not effective_org_id:
        raise UserError("Organization access could not be verified.")
    if getattr(context, "is_platform_admin", False) is True:
        return effective_org_id
    if not current_org_id or str(effective_org_id) != str(current_org_id):
        raise UserError("Organization access denied.")
    return effective_org_id
