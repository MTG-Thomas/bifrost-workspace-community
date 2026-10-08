"""
HaloPSA SQL Execution Tool
"""
from bifrost import tool, UserError
from modules.extensions.platform_auth import require_platform_admin
from modules.extensions.halopsa import execute_sql
import logging
import re

logger = logging.getLogger(__name__)
MAX_ROWS = 100
PREVIEW_ROWS = 20

@tool(
    name="Execute HaloPSA SQL",
    description="Execute a SQL query against the HaloPSA reporting database and return structured results.",
)
async def execute_halopsa_sql(query: str, max_rows: int = MAX_ROWS, preview: bool = False) -> dict:
    require_platform_admin()
    stripped = query.strip().upper()
    if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
        raise UserError("Only SELECT and WITH (CTE) queries are allowed.")
    effective_max = max(1, min(max_rows, 500))
    if preview: effective_max = PREVIEW_ROWS
    # A TOP in a string, comment, or nested query does not cap the outer SELECT.
    has_outer_top = bool(re.match(r"SELECT\s+(?:DISTINCT\s+)?TOP\s*(?:\(|\d)", stripped))
    needs_top = stripped.startswith("SELECT") and not has_outer_top
    execute_query = query
    if needs_top and stripped.startswith("SELECT"):
        fetch_limit = effective_max + 1
        execute_query = query.strip()
        if stripped.startswith("SELECT DISTINCT"):
            execute_query = f"SELECT DISTINCT TOP {fetch_limit} {execute_query[15:].lstrip()}"
        else:
            execute_query = f"SELECT TOP {fetch_limit} {execute_query[6:].lstrip()}"
    try:
        rows = await execute_sql(execute_query)
    except UserError: raise
    except Exception as e:
        logger.error(f"HaloPSA SQL tool error: {e}")
        return {"success": False, "row_count": 0, "total_estimated": 0, "truncated": False,
                "columns": [], "rows": [], "query": query, "error": str(e)}
    truncated = False
    # Always cap returned data, including CTEs and queries with their own TOP.
    if len(rows) > effective_max:
        truncated = True
        rows = rows[:effective_max]
    columns = list(rows[0].keys()) if rows else []
    return {"success": True, "row_count": len(rows),
            "total_estimated": f">{effective_max}" if truncated else len(rows),
            "truncated": truncated, "columns": columns, "rows": rows, "query": query}
