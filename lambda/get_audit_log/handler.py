"""Audit Log Lambda handler.

Routes:
- GET /audit-log?resource_id=X  — entries for a specific resource (base table)
- GET /audit-log?user=X         — entries for a specific user (user-index GSI)
- GET /audit-log                — scan recent entries (fallback)

Table schema: PK=resource_id, SK=timestamp, GSI user-index(user_id, timestamp)
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from boto3.dynamodb.conditions import Key
from rbac import require_role
from utils import (
    build_error_response,
    build_success_response,
    get_dynamodb_table,
    get_query_parameter,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _get_audit_table():
    return get_dynamodb_table(os.environ.get("AUDIT_LOG_TABLE_NAME", "bbp-hkbg-audit-log"))


def _format_entry(e):
    return {
        "timestamp": e.get("timestamp", ""),
        "user_id": e.get("user_id", ""),
        "user_name": e.get("user_name", ""),
        "action_type": e.get("action_type", ""),
        "resource_type": e.get("resource_type", ""),
        "resource_id": e.get("resource_id", ""),
        "details": e.get("details"),
    }


def _query_by_resource(resource_id):
    """Query all audit entries for a resource, newest first."""
    table = _get_audit_table()
    items = []
    kwargs = {
        "KeyConditionExpression": Key("resource_id").eq(resource_id),
        "ScanIndexForward": False,
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def _query_by_user(user_id):
    """Query all audit entries for a user via GSI, newest first."""
    table = _get_audit_table()
    items = []
    kwargs = {
        "IndexName": "user-index",
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "ScanIndexForward": False,
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def _scan_recent(limit=100):
    """Scan for recent entries (no filter — fallback for browsing)."""
    table = _get_audit_table()
    resp = table.scan(Limit=limit)
    items = resp.get("Items", [])
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items


@require_role("admin")
def handler(event, context, user_context):
    method = event.get("httpMethod", "GET").upper()
    if method != "GET":
        return build_error_response(405, "Method not allowed")

    resource_id = get_query_parameter(event, "resource_id")
    user_filter = get_query_parameter(event, "user")

    try:
        if resource_id:
            entries = _query_by_resource(resource_id)
        elif user_filter:
            entries = _query_by_user(user_filter)
        else:
            entries = _scan_recent()
    except Exception:
        logger.exception("Failed to query audit log")
        return build_error_response(500, "Failed to query audit log")

    result = [_format_entry(e) for e in entries]
    return build_success_response({"entries": result, "count": len(result)})
