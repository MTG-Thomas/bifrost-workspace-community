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
