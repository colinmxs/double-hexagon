"""Audit Log Lambda handler.

Routes:
- GET  /audit-log        — Query audit log entries (reverse chronological)
- POST /audit-log/export — Export filtered entries as CSV

Requirements: 15.6, 15.7, 15.8, 15.9
"""

import csv
import io
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from boto3.dynamodb.conditions import Key, Attr
from rbac import require_role
from utils import (
    build_error_response,
    build_success_response,
    get_dynamodb_table,
    get_query_parameter,
    parse_request_body,
    CORS_HEADERS,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _get_audit_table():
    table_name = os.environ.get("AUDIT_LOG_TABLE_NAME", "bbp-hkbg-audit-log")
    return get_dynamodb_table(table_name)


def _build_filter(params):
    """Build a FilterExpression from query parameters."""
    conditions = []
    values = {}
    names = {}

    user_filter = params.get("user")
    if user_filter:
        conditions.append("#uid = :uid")
        names["#uid"] = "user_id"
        values[":uid"] = user_filter

    action_filter = params.get("action_type")
    if action_filter:
        conditions.append("#at = :at")
        names["#at"] = "action_type"
        values[":at"] = action_filter

    resource_filter = params.get("resource_type")
    if resource_filter:
        conditions.append("#rt = :rt")
        names["#rt"] = "resource_type"
        values[":rt"] = resource_filter

    return conditions, names, values


def _query_entries(params):
    """Query audit log entries with optional filters."""
    table = _get_audit_table()

    date_from = params.get("date_from")
    date_to = params.get("date_to")

    # Determine year_month partitions to query
    if date_from and date_to:
        partitions = _get_month_partitions(date_from, date_to)
    elif date_from:
        partitions = _get_month_partitions(date_from, "2099-12")
    elif date_to:
        partitions = _get_month_partitions("2020-01", date_to)
    else:
        # Default: last 3 months
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        partitions = []
        for i in range(3):
            d = now - timedelta(days=30 * i)
            partitions.append(d.strftime("%Y-%m"))

    conditions, names, values = _build_filter(params)

    # Add date range filter on timestamp
    if date_from:
        conditions.append("#ts >= :df")
        names["#ts"] = "timestamp"
        values[":df"] = date_from
    if date_to:
        if "#ts" not in names:
            names["#ts"] = "timestamp"
        conditions.append("#ts <= :dt")
        values[":dt"] = date_to + "T23:59:59.999Z" if "T" not in date_to else date_to

    all_items = []
    for partition in partitions:
        query_kwargs = {
            "KeyConditionExpression": Key("year_month").eq(partition),
            "ScanIndexForward": False,
        }
        if conditions:
            query_kwargs["FilterExpression"] = " AND ".join(conditions)
        if names:
            query_kwargs["ExpressionAttributeNames"] = names
        if values:
            query_kwargs["ExpressionAttributeValues"] = values

        resp = table.query(**query_kwargs)
        all_items.extend(resp.get("Items", []))

    # Sort all items reverse chronological
    all_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return all_items


def _get_month_partitions(date_from, date_to):
    """Generate YYYY-MM partition keys between two dates."""
    from datetime import datetime
    partitions = []
    try:
        start = datetime.strptime(date_from[:7], "%Y-%m")
        end = datetime.strptime(date_to[:7], "%Y-%m")
    except (ValueError, TypeError):
        return partitions
    current = start
    while current <= end:
        partitions.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return partitions


@require_role("admin")
def handler(event, context, user_context):
    method = event.get("httpMethod", "GET").upper()
    path = event.get("path", "")

    if "export" in path and method == "POST":
        return _handle_export(event)
    if method == "GET":
        return _handle_query(event)
    return build_error_response(405, "Method not allowed")


def _handle_query(event):
    params = {
        "user": get_query_parameter(event, "user"),
        "action_type": get_query_parameter(event, "action_type"),
        "resource_type": get_query_parameter(event, "resource_type"),
        "date_from": get_query_parameter(event, "date_from"),
        "date_to": get_query_parameter(event, "date_to"),
    }
    params = {k: v for k, v in params.items() if v}

    try:
        entries = _query_entries(params)
    except Exception:
        logger.exception("Failed to query audit log")
        return build_error_response(500, "Failed to query audit log")

    result = []
    for e in entries:
        result.append({
            "timestamp": e.get("timestamp", ""),
            "user_id": e.get("user_id", ""),
            "user_name": e.get("user_name", ""),
            "action_type": e.get("action_type", ""),
            "resource_type": e.get("resource_type", ""),
            "resource_id": e.get("resource_id", ""),
            "details": e.get("details"),
        })

    return build_success_response({"entries": result, "count": len(result)})


def _handle_export(event):
    try:
        body = parse_request_body(event)
    except ValueError:
        body = {}

    params = {
        "user": body.get("user"),
        "action_type": body.get("action_type"),
        "resource_type": body.get("resource_type"),
        "date_from": body.get("date_from"),
        "date_to": body.get("date_to"),
    }
    params = {k: v for k, v in params.items() if v}

    try:
        entries = _query_entries(params)
    except Exception:
        logger.exception("Failed to query audit log for export")
        return build_error_response(500, "Failed to export audit log")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "User ID", "User Name", "Action Type", "Resource Type", "Resource ID", "Details"])
    for e in entries:
        details = json.dumps(e.get("details")) if e.get("details") else ""
        writer.writerow([
            e.get("timestamp", ""),
            e.get("user_id", ""),
            e.get("user_name", ""),
            e.get("action_type", ""),
            e.get("resource_type", ""),
            e.get("resource_id", ""),
            details,
        ])

    return {
        "statusCode": 200,
        "headers": {
            **CORS_HEADERS,
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=audit_log.csv",
        },
        "body": output.getvalue(),
    }
