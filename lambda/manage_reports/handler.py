"""Manage Reports Lambda handler — CRUD for Saved Reports.

Provides endpoints to save, list, load, update, and delete report
configurations stored in the Saved Reports DynamoDB table.

HTTP methods:
- GET (no report_id): List saved reports for current user
- GET (with report_id path param): Load a specific saved report
- POST: Create a new saved report
- PUT: Update an existing saved report
- DELETE: Delete a saved report

Requirements: 11.8, 11.9, 11.10
"""

import logging
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from audit_middleware import log_audit_from_context
from rbac import require_role
from utils import (
    build_error_response,
    build_success_response,
    get_dynamodb_table,
    get_path_parameter,
    parse_request_body,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SAVED_REPORTS_TABLE = os.environ.get(
    "SAVED_REPORTS_TABLE_NAME", "bbp-hkbg-saved-reports"
)


def _get_table():
    """Return the Saved Reports DynamoDB table resource."""
    return get_dynamodb_table(SAVED_REPORTS_TABLE)


def _generate_report_id():
    """Generate a unique report ID."""
    return f"rpt-{uuid.uuid4().hex[:12]}"


def _now_iso():
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_report_body(body):
    """Validate required fields for creating/updating a saved report.

    Args:
        body: Parsed request body dict.

    Returns:
        Tuple of (error_message, None) on failure, or (None, validated_data) on success.
    """
    name = body.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        return "Report name is required", None

    columns = body.get("columns", [])
    if not isinstance(columns, list):
        return "columns must be a list", None

    filters = body.get("filters", [])
    if not isinstance(filters, list):
        return "filters must be a list", None

    group_by = body.get("group_by")
    sort_by = body.get("sort_by")
    sort_order = body.get("sort_order", "asc")

    if sort_order not in ("asc", "desc"):
        sort_order = "asc"

    return None, {
        "name": name.strip(),
        "columns": columns,
        "filters": filters,
        "group_by": group_by,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


def _create_report(event, user_context):
    """Create a new saved report configuration.

    Requirement 11.8: Save a report configuration with a user-defined name.
    """
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    error, data = _validate_report_body(body)
    if error:
        return build_error_response(400, error)

    user_id = user_context.get("user_id", "unknown")
    report_id = _generate_report_id()
    now = _now_iso()

    item = {
        "user_id": user_id,
        "report_id": report_id,
        "name": data["name"],
        "columns": data["columns"],
        "filters": data["filters"],
        "group_by": data["group_by"],
        "sort_by": data["sort_by"],
        "sort_order": data["sort_order"],
        "created_at": now,
        "updated_at": now,
    }

    try:
        table = _get_table()
        table.put_item(Item=item)
    except Exception:
        logger.exception("Failed to create saved report")
        return build_error_response(500, "Failed to save report")

    log_audit_from_context(
        user_context,
        action_type="create",
        resource_type="report",
        resource_id=report_id,
        details={"report_name": data["name"]},
    )

    return build_success_response(item, status_code=201)


def _list_reports(user_context):
    """List all saved reports for the current user.

    Requirement 11.9: Display a list of saved reports.
    """
    user_id = user_context.get("user_id", "unknown")

    try:
        from boto3.dynamodb.conditions import Key

        table = _get_table()
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
        )
        items = response.get("Items", [])
    except Exception:
        logger.exception("Failed to list saved reports")
        return build_error_response(500, "Failed to list saved reports")

    return build_success_response({"reports": items})


def _load_report(report_id, user_context):
    """Load a specific saved report by ID.

    Requirement 11.10: Restore all previously configured columns, filters,
    groupings, and sort order.
    """
    user_id = user_context.get("user_id", "unknown")

    try:
        table = _get_table()
        response = table.get_item(
            Key={"user_id": user_id, "report_id": report_id}
        )
    except Exception:
        logger.exception("Failed to load saved report")
        return build_error_response(500, "Failed to load saved report")

    item = response.get("Item")
    if not item:
        return build_error_response(404, "Saved report not found")

    return build_success_response(item)


def _update_report(event, report_id, user_context):
    """Update an existing saved report configuration."""
    user_id = user_context.get("user_id", "unknown")

    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    error, data = _validate_report_body(body)
    if error:
        return build_error_response(400, error)

    # Verify the report exists and belongs to the user
    try:
        table = _get_table()
        existing = table.get_item(
            Key={"user_id": user_id, "report_id": report_id}
        )
    except Exception:
        logger.exception("Failed to check existing report")
        return build_error_response(500, "Failed to update report")

    if not existing.get("Item"):
        return build_error_response(404, "Saved report not found")

    now = _now_iso()
    item = {
        "user_id": user_id,
        "report_id": report_id,
        "name": data["name"],
        "columns": data["columns"],
        "filters": data["filters"],
        "group_by": data["group_by"],
        "sort_by": data["sort_by"],
        "sort_order": data["sort_order"],
        "created_at": existing["Item"].get("created_at", now),
        "updated_at": now,
    }

    try:
        table.put_item(Item=item)
    except Exception:
        logger.exception("Failed to update saved report")
        return build_error_response(500, "Failed to update report")

    log_audit_from_context(
        user_context,
        action_type="update",
        resource_type="report",
        resource_id=report_id,
        details={"report_name": data["name"]},
    )

    return build_success_response(item)


def _delete_report(report_id, user_context):
    """Delete a saved report.

    Requirement 11.9: Allow deletion of saved reports.
    """
    user_id = user_context.get("user_id", "unknown")

    # Verify the report exists and belongs to the user
    try:
        table = _get_table()
        existing = table.get_item(
            Key={"user_id": user_id, "report_id": report_id}
        )
    except Exception:
        logger.exception("Failed to check existing report for deletion")
        return build_error_response(500, "Failed to delete report")

    if not existing.get("Item"):
        return build_error_response(404, "Saved report not found")

    try:
        table.delete_item(Key={"user_id": user_id, "report_id": report_id})
    except Exception:
        logger.exception("Failed to delete saved report")
        return build_error_response(500, "Failed to delete report")

    log_audit_from_context(
        user_context,
        action_type="delete",
        resource_type="report",
        resource_id=report_id,
    )

    return build_success_response({"message": "Report deleted", "report_id": report_id})


@require_role("admin", "reporter")
def handler(event, context, user_context):
    """Route requests to the appropriate CRUD operation.

    Routing:
    - POST /api/reports/saved → create
    - GET  /api/reports/saved → list
    - GET  /api/reports/saved/{id} → load
    - PUT  /api/reports/saved/{id} → update
    - DELETE /api/reports/saved/{id} → delete

    Requirements: 11.8, 11.9, 11.10
    """
    http_method = event.get("httpMethod", "").upper()
    report_id = get_path_parameter(event, "id")

    if http_method == "POST":
        return _create_report(event, user_context)

    elif http_method == "GET":
        if report_id:
            return _load_report(report_id, user_context)
        return _list_reports(user_context)

    elif http_method == "PUT":
        if not report_id:
            return build_error_response(400, "Report ID is required for update")
        return _update_report(event, report_id, user_context)

    elif http_method == "DELETE":
        if not report_id:
            return build_error_response(400, "Report ID is required for deletion")
        return _delete_report(report_id, user_context)

    elif http_method == "OPTIONS":
        return build_success_response({})

    else:
        return build_error_response(405, f"Method {http_method} not allowed")
