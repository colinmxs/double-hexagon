"""Run Report Lambda handler.

Executes report queries with filters, grouping, aggregation, and pagination.
Accepts a report configuration body with selected columns, multiple filters
(field-type-appropriate operators), group-by column, sort column/order.
Computes summary statistics and enforces giveaway year scoping for reporters.

Also provides a CSV export endpoint (POST /api/reports/export) that generates
a downloadable CSV with visible columns and applied filters, and records an
audit log entry for the export action.

Requirements: 11.2, 11.3, 11.4, 11.5, 11.7, 11.11, 11.13, 11.14, 14.6, 15.5
"""

import csv
import io
import json
import logging
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from audit_middleware import log_audit_from_context
from rbac import enforce_year_scoping, require_role
from utils import (
    build_error_response,
    build_success_response,
    get_dynamodb_table,
    parse_request_body,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

VALID_OPERATORS = {"equals", "contains", "greater_than", "less_than", "between", "in_list"}

VALID_SORT_ORDERS = {"asc", "desc"}


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that converts Decimal to int or float."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def _resolve_field(item, field_path):
    """Resolve a dot/bracket-notated field path to a value in a nested dict.

    Supports paths like:
      - "status"
      - "parent_guardian.first_name"
      - "children[0].height_inches"
      - "referring_agency.agency_name"

    Args:
        item: The application dict.
        field_path: Dot/bracket-notated path string.

    Returns:
        The resolved value, or None if the path doesn't exist.
    """
    # Split on dots, then handle bracket notation within each segment
    parts = field_path.split(".")
    current = item

    for part in parts:
        if current is None:
            return None

        # Check for array index notation like "children[0]"
        bracket_match = re.match(r"^(\w+)\[(\d+)\]$", part)
        if bracket_match:
            key = bracket_match.group(1)
            index = int(bracket_match.group(2))
            if isinstance(current, dict) and key in current:
                arr = current[key]
                if isinstance(arr, list) and 0 <= index < len(arr):
                    current = arr[index]
                else:
                    return None
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None

    return current


def _to_number(value):
    """Attempt to convert a value to a numeric type for comparison."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return None


def _apply_filter(item, filter_def):
    """Apply a single filter to an application item.

    Args:
        item: Application dict.
        filter_def: Dict with 'field', 'operator', and 'value'.

    Returns:
        True if the item passes the filter, False otherwise.
    """
    field = filter_def.get("field", "")
    operator = filter_def.get("operator", "")
    filter_value = filter_def.get("value")

    if operator not in VALID_OPERATORS:
        return True  # Skip invalid operators

    item_value = _resolve_field(item, field)

    if operator == "equals":
        if item_value is None:
            return filter_value is None
        # Handle Decimal comparison
        item_num = _to_number(item_value)
        filter_num = _to_number(filter_value)
        if item_num is not None and filter_num is not None:
            return item_num == filter_num
        return str(item_value).lower() == str(filter_value).lower()

    elif operator == "contains":
        if item_value is None or filter_value is None:
            return False
        return str(filter_value).lower() in str(item_value).lower()

    elif operator == "greater_than":
        item_num = _to_number(item_value)
        filter_num = _to_number(filter_value)
        if item_num is None or filter_num is None:
            return False
        return item_num > filter_num

    elif operator == "less_than":
        item_num = _to_number(item_value)
        filter_num = _to_number(filter_value)
        if item_num is None or filter_num is None:
            return False
        return item_num < filter_num

    elif operator == "between":
        if not isinstance(filter_value, list) or len(filter_value) != 2:
            return False
        item_num = _to_number(item_value)
        low = _to_number(filter_value[0])
        high = _to_number(filter_value[1])
        if item_num is None or low is None or high is None:
            return False
        return low <= item_num <= high

    elif operator == "in_list":
        if not isinstance(filter_value, list):
            return False
        if item_value is None:
            return False
        str_value = str(item_value).lower()
        return str_value in [str(v).lower() for v in filter_value]

    return True


def _apply_filters(item, filters):
    """Apply all filters to an item. All filters must pass (AND logic).

    Args:
        item: Application dict.
        filters: List of filter dicts.

    Returns:
        True if the item passes all filters.
    """
    for f in filters:
        if not _apply_filter(item, f):
            return False
    return True


def _extract_columns(item, columns):
    """Extract selected columns from an application item.

    Args:
        item: Application dict.
        columns: List of field path strings.

    Returns:
        Dict mapping column path to resolved value.
    """
    row = {}
    for col in columns:
        value = _resolve_field(item, col)
        # Convert Decimal for JSON serialization
        if isinstance(value, Decimal):
            value = int(value) if value % 1 == 0 else float(value)
        elif isinstance(value, list):
            value = [
                (int(v) if isinstance(v, Decimal) and v % 1 == 0 else float(v))
                if isinstance(v, Decimal)
                else v
                for v in value
            ]
        row[col] = value
    return row


def _sort_items(items, sort_by, sort_order):
    """Sort items by a field path.

    Args:
        items: List of application dicts.
        sort_by: Field path to sort by.
        sort_order: 'asc' or 'desc'.

    Returns:
        Sorted list.
    """
    reverse = sort_order == "desc"

    def sort_key(item):
        value = _resolve_field(item, sort_by)
        if value is None:
            # Push None values to the end
            return (1, "")
        num = _to_number(value)
        if num is not None:
            return (0, num)
        return (0, str(value).lower())

    return sorted(items, key=sort_key, reverse=reverse)


def _compute_summary(items):
    """Compute summary statistics for the report.

    Args:
        items: List of application dicts (after filtering).

    Returns:
        Dict with total_applications, total_children,
        applications_by_status, applications_by_source_type.
    """
    total_applications = len(items)
    total_children = 0
    by_status = {}
    by_source = {}

    for item in items:
        children = item.get("children", [])
        total_children += len(children) if isinstance(children, list) else 0

        status = item.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        source = item.get("source_type", "unknown")
        by_source[source] = by_source.get(source, 0) + 1

    return {
        "total_applications": total_applications,
        "total_children": total_children,
        "applications_by_status": by_status,
        "applications_by_source_type": by_source,
    }


def _group_items(rows, group_by):
    """Group extracted rows by a column value.

    Args:
        rows: List of row dicts (extracted columns).
        group_by: Column path to group by.

    Returns:
        Dict mapping group value to list of rows.
    """
    groups = {}
    for row in rows:
        group_value = row.get(group_by)
        if group_value is None:
            group_key = "null"
        elif isinstance(group_value, bool):
            group_key = str(group_value).lower()
        else:
            group_key = str(group_value)
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(row)
    return groups


def _paginate(items, page, page_size):
    """Apply pagination to a list of items.

    Args:
        items: Full list of items.
        page: 1-based page number.
        page_size: Number of items per page.

    Returns:
        Tuple of (page_items, total_pages, total_count).
    """
    total_count = len(items)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total_pages, total_count


def _get_active_giveaway_year():
    """Read the active giveaway year from the Config table."""
    config_table_name = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    table = get_dynamodb_table(config_table_name)
    response = table.get_item(Key={"config_key": "active_giveaway_year"})
    item = response.get("Item")
    if not item or "value" not in item:
        return None
    return str(item["value"])


def _fetch_all_items(table, giveaway_year):
    """Fetch all application items for a giveaway year using pagination.

    Args:
        table: DynamoDB Table resource.
        giveaway_year: The giveaway year partition key.

    Returns:
        List of all application dicts.
    """
    from boto3.dynamodb.conditions import Key

    all_items = []
    kwargs = {
        "KeyConditionExpression": Key("giveaway_year").eq(giveaway_year),
    }

    while True:
        response = table.query(**kwargs)
        all_items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return all_items


@require_role("admin", "reporter")
def handler(event, context, user_context):
    """Execute a report query with filters, grouping, aggregation, and pagination.

    Accepts POST body:
    {
        "giveaway_year": "2025",
        "columns": ["parent_guardian.first_name", ...],
        "filters": [{"field": "status", "operator": "equals", "value": "..."}],
        "group_by": "status",
        "sort_by": "parent_guardian.last_name",
        "sort_order": "asc",
        "page": 1,
        "page_size": 50
    }

    Requirements: 11.2, 11.3, 11.4, 11.5, 11.7, 11.13, 11.14, 14.6
    """
    # Parse request body
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    # Extract configuration
    giveaway_year = body.get("giveaway_year")
    columns = body.get("columns", [])
    filters = body.get("filters", [])
    group_by = body.get("group_by")
    sort_by = body.get("sort_by")
    sort_order = body.get("sort_order", "asc")
    page = body.get("page", 1)
    page_size = body.get("page_size", DEFAULT_PAGE_SIZE)

    # Validate inputs
    if not isinstance(columns, list):
        return build_error_response(400, "columns must be a list")

    if not isinstance(filters, list):
        return build_error_response(400, "filters must be a list")

    # Validate filters
    for f in filters:
        if not isinstance(f, dict):
            return build_error_response(400, "Each filter must be an object")
        if "field" not in f or "operator" not in f:
            return build_error_response(400, "Each filter must have field and operator")
        if f["operator"] not in VALID_OPERATORS:
            return build_error_response(
                400,
                f"Invalid filter operator: {f['operator']}. "
                f"Valid operators: {', '.join(sorted(VALID_OPERATORS))}",
            )

    if sort_order not in VALID_SORT_ORDERS:
        sort_order = "asc"

    # Clamp page_size
    try:
        page_size = int(page_size)
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE

    # Clamp page
    try:
        page = int(page)
        page = max(1, page)
    except (TypeError, ValueError):
        page = 1

    # Default to active giveaway year if not specified
    if not giveaway_year:
        try:
            giveaway_year = _get_active_giveaway_year()
        except Exception:
            logger.exception("Failed to read active giveaway year")
            return build_error_response(500, "Failed to determine active giveaway year")
        if not giveaway_year:
            return build_error_response(500, "No active giveaway year configured")

    giveaway_year = str(giveaway_year)

    # Enforce year scoping for reporter role (Requirement 14.6)
    if not enforce_year_scoping(user_context, giveaway_year):
        return build_error_response(
            403, "Forbidden: not authorized for this giveaway year"
        )

    # Fetch all items for the giveaway year
    try:
        table_name = os.environ.get(
            "APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"
        )
        table = get_dynamodb_table(table_name)
        all_items = _fetch_all_items(table, giveaway_year)
    except Exception:
        logger.exception("Failed to query applications for report")
        return build_error_response(500, "Failed to retrieve report data")

    # Apply filters (Requirement 11.3)
    filtered_items = [item for item in all_items if _apply_filters(item, filters)]

    # Compute summary statistics (Requirement 11.5)
    summary = _compute_summary(filtered_items)

    # Sort (Requirement 11.7)
    if sort_by:
        filtered_items = _sort_items(filtered_items, sort_by, sort_order)

    # Paginate (Requirement 11.14)
    page_items, total_pages, total_count = _paginate(
        filtered_items, page, page_size
    )

    # Extract selected columns for the page
    if columns:
        rows = [_extract_columns(item, columns) for item in page_items]
    else:
        # If no columns specified, return full items (with Decimal conversion)
        rows = json.loads(json.dumps(page_items, cls=DecimalEncoder))

    # Group by (Requirement 11.4)
    groups = None
    if group_by:
        # Group all filtered items (not just the page) for accurate counts
        all_rows_for_grouping = [
            _extract_columns(item, columns if columns else [group_by])
            for item in filtered_items
        ]
        raw_groups = _group_items(all_rows_for_grouping, group_by)
        groups = {k: {"count": len(v)} for k, v in raw_groups.items()}

    # Build response
    result = {
        "summary": summary,
        "rows": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        },
        "giveaway_year": giveaway_year,
    }

    if groups is not None:
        result["groups"] = groups

    return build_success_response(result)

def _format_csv_value(value):
    """Format a value for CSV output.

    Args:
        value: Any value from an application record.

    Returns:
        String representation suitable for CSV.
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(int(value) if value % 1 == 0 else float(value))
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, bool):
        return str(value)
    return str(value)


def _generate_csv(columns, rows):
    """Generate a CSV string from column headers and row data.

    Args:
        columns: List of column path strings used as headers.
        rows: List of dicts mapping column paths to values.

    Returns:
        CSV string with header row and data rows.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(columns)

    # Data rows
    for row in rows:
        writer.writerow([_format_csv_value(row.get(col)) for col in columns])

    return output.getvalue()


ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:4173",
).split(",")


def _get_export_cors_headers(event=None):
    """Return CORS headers for the export handler, reflecting the request origin."""
    origin = None
    if event:
        headers = event.get("headers") or {}
        origin = headers.get("origin") or headers.get("Origin")
    if "*" in ALLOWED_ORIGINS:
        allow_origin = "*"
    elif origin and origin in ALLOWED_ORIGINS:
        allow_origin = origin
    else:
        allow_origin = ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else ""
    return {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Vary": "Origin",
    }


@require_role("admin", "reporter")
def export_handler(event, context, user_context):
    """Export report results as a CSV file.

    Accepts the same POST body as the run report handler (columns, filters,
    sort_by, sort_order, giveaway_year) but returns a CSV download instead
    of JSON. Records an audit log entry for the export action.

    Requirements: 11.11, 15.5
    """
    # Parse request body
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    # Extract configuration
    giveaway_year = body.get("giveaway_year")
    columns = body.get("columns", [])
    filters = body.get("filters", [])
    sort_by = body.get("sort_by")
    sort_order = body.get("sort_order", "asc")

    # Validate inputs
    if not isinstance(columns, list) or not columns:
        return build_error_response(400, "columns must be a non-empty list")

    if not isinstance(filters, list):
        return build_error_response(400, "filters must be a list")

    for f in filters:
        if not isinstance(f, dict):
            return build_error_response(400, "Each filter must be an object")
        if "field" not in f or "operator" not in f:
            return build_error_response(
                400, "Each filter must have field and operator"
            )
        if f["operator"] not in VALID_OPERATORS:
            return build_error_response(
                400,
                f"Invalid filter operator: {f['operator']}. "
                f"Valid operators: {', '.join(sorted(VALID_OPERATORS))}",
            )

    if sort_order not in VALID_SORT_ORDERS:
        sort_order = "asc"

    # Default to active giveaway year if not specified
    if not giveaway_year:
        try:
            giveaway_year = _get_active_giveaway_year()
        except Exception:
            logger.exception("Failed to read active giveaway year")
            return build_error_response(
                500, "Failed to determine active giveaway year"
            )
        if not giveaway_year:
            return build_error_response(
                500, "No active giveaway year configured"
            )

    giveaway_year = str(giveaway_year)

    # Enforce year scoping for reporter role (Requirement 14.6)
    if not enforce_year_scoping(user_context, giveaway_year):
        return build_error_response(
            403, "Forbidden: not authorized for this giveaway year"
        )

    # Fetch all items for the giveaway year
    try:
        table_name = os.environ.get(
            "APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"
        )
        table = get_dynamodb_table(table_name)
        all_items = _fetch_all_items(table, giveaway_year)
    except Exception:
        logger.exception("Failed to query applications for report export")
        return build_error_response(500, "Failed to retrieve report data")

    # Apply filters (Requirement 11.3)
    filtered_items = [
        item for item in all_items if _apply_filters(item, filters)
    ]

    # Sort (Requirement 11.7)
    if sort_by:
        filtered_items = _sort_items(filtered_items, sort_by, sort_order)

    # Extract selected columns for all filtered items (no pagination for export)
    rows = [_extract_columns(item, columns) for item in filtered_items]

    # Generate CSV (Requirement 11.11)
    csv_content = _generate_csv(columns, rows)

    # Record audit log entry for export action (Requirement 15.5)
    filter_summary = [
        {"field": f.get("field"), "operator": f.get("operator")}
        for f in filters
    ]
    log_audit_from_context(
        user_context,
        action_type="export",
        resource_type="report",
        resource_id=f"report_export_{giveaway_year}",
        details={
            "export_type": "report",
            "giveaway_year": giveaway_year,
            "columns": columns,
            "filters_applied": filter_summary,
            "row_count": len(rows),
        },
    )

    # Return CSV response with appropriate headers
    return {
        "statusCode": 200,
        "headers": {
            **_get_export_cors_headers(event),
            "Content-Type": "text/csv",
            "Content-Disposition": "attachment; filename=\"report_export.csv\"",
        },
        "body": csv_content,
    }
