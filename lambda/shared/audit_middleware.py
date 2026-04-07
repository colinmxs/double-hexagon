"""Shared audit logging middleware used by other Lambda functions.

Writes audit log entries to the Audit Log DynamoDB table.
Records: user_id, user_name, timestamp, action_type, resource_type,
resource_id, and optional details (field name, previous value, new value).

PII values are NEVER logged to CloudWatch Logs (Requirement 16.10).

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 16.10
"""

import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Valid action types per the design doc
VALID_ACTION_TYPES = frozenset(
    ["view", "create", "update", "delete", "export", "login", "logout"]
)


def _get_audit_table():
    """Return a DynamoDB Table resource for the Audit Log table."""
    table_name = os.environ.get("AUDIT_LOG_TABLE_NAME", "bbp-hkbg-audit-log")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def log_audit_event(
    user_id,
    user_name,
    action_type,
    resource_type,
    resource_id,
    details=None,
):
    """Write an audit log entry to the Audit Log DynamoDB table.

    Args:
        user_id: Identifier of the user performing the action.
        user_name: Display name of the user.
        action_type: One of view, create, update, delete, export, login, logout.
        resource_type: Type of resource acted upon (e.g. application, user_account).
        resource_id: Identifier of the specific resource.
        details: Optional dict with extra context (e.g. field_name,
            previous_value, new_value for updates). PII values in details
            are stored in DynamoDB but never logged to CloudWatch.

    Returns:
        The audit log item dict on success, or None on failure.
    """
    now = datetime.now(timezone.utc)
    timestamp_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    item = {
        "resource_id": str(resource_id),
        "timestamp": timestamp_iso,
        "user_id": str(user_id),
        "user_name": str(user_name),
        "action_type": str(action_type),
        "resource_type": str(resource_type),
    }

    if details is not None:
        item["details"] = details

    # Log the action WITHOUT any PII (Requirement 16.10)
    logger.info(
        "Audit event: action_type=%s resource_type=%s resource_id=%s user_id=%s",
        action_type,
        resource_type,
        resource_id,
        user_id,
    )

    try:
        table = _get_audit_table()
        table.put_item(Item=item)
    except ClientError:
        logger.error(
            "Failed to write audit log entry: action_type=%s resource_type=%s resource_id=%s",
            action_type,
            resource_type,
            resource_id,
        )
        return None

    return item


def log_audit_from_context(
    user_context,
    action_type,
    resource_type,
    resource_id,
    details=None,
):
    """Convenience wrapper that extracts user info from auth middleware context.

    Args:
        user_context: Dict returned by auth_middleware.authenticate(),
            must contain 'user_id' and 'name' keys.
        action_type: One of view, create, update, delete, export, login, logout.
        resource_type: Type of resource acted upon.
        resource_id: Identifier of the specific resource.
        details: Optional dict with extra context.

    Returns:
        The audit log item dict on success, or None on failure.
    """
    user_id = user_context.get("user_id", "unknown")
    user_name = user_context.get("name", "Unknown User")

    return log_audit_event(
        user_id=user_id,
        user_name=user_name,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
