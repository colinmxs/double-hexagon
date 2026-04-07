"""Get/Update Confidence Threshold Lambda handler.

Read and update the confidence threshold from the Config DynamoDB table.
- GET: Returns the current confidence threshold (default 0.80 if not set).
- PUT: Updates the confidence threshold (must be a number between 0.0 and 1.0).

Admin-only endpoint. Records audit log entries for updates.

Requirements: 4.5
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from audit_middleware import log_audit_from_context
from rbac import require_role
from utils import (
    build_error_response,
    build_success_response,
    get_dynamodb_table,
    parse_request_body,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_CONFIDENCE_THRESHOLD = "0.80"
CONFIG_KEY = "confidence_threshold"


def _get_config_table():
    """Return the Config DynamoDB table resource."""
    table_name = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    return get_dynamodb_table(table_name)


def _read_threshold():
    """Read the confidence threshold from the Config table.

    Returns:
        str: The threshold value as a string, or the default if not set.
    """
    table = _get_config_table()
    response = table.get_item(Key={"config_key": CONFIG_KEY})
    item = response.get("Item")
    if not item or "value" not in item:
        return DEFAULT_CONFIDENCE_THRESHOLD
    return str(item["value"])


def _write_threshold(value):
    """Write the confidence threshold to the Config table.

    Args:
        value: The threshold value as a string.
    """
    table = _get_config_table()
    table.put_item(Item={"config_key": CONFIG_KEY, "value": value})


@require_role("admin")
def handler(event, context, user_context):
    """Handle GET/PUT for confidence threshold configuration.

    GET: Returns {"confidence_threshold": "0.80"}
    PUT: Accepts {"value": 0.75} and updates the threshold.

    Requirements: 4.5
    """
    http_method = event.get("httpMethod", "GET").upper()

    if http_method == "GET":
        return _handle_get()
    elif http_method == "PUT":
        return _handle_put(event, user_context)
    else:
        return build_error_response(405, "Method not allowed")


def _handle_get():
    """Handle GET request — read current confidence threshold."""
    try:
        threshold = _read_threshold()
    except Exception:
        logger.exception("Failed to read confidence threshold")
        return build_error_response(500, "Failed to read confidence threshold")

    return build_success_response({"confidence_threshold": threshold})


def _handle_put(event, user_context):
    """Handle PUT request — update confidence threshold."""
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    raw_value = body.get("value")
    if raw_value is None:
        return build_error_response(400, "Missing required field: value")

    # Validate the value is a number between 0.0 and 1.0
    try:
        threshold = float(raw_value)
    except (TypeError, ValueError):
        return build_error_response(400, "Value must be a number between 0.0 and 1.0")

    if threshold < 0.0 or threshold > 1.0:
        return build_error_response(400, "Value must be a number between 0.0 and 1.0")

    # Read previous value for audit log
    try:
        previous_value = _read_threshold()
    except Exception:
        previous_value = DEFAULT_CONFIDENCE_THRESHOLD

    # Format as string with two decimal places
    new_value = f"{threshold:.2f}"

    try:
        _write_threshold(new_value)
    except Exception:
        logger.exception("Failed to update confidence threshold")
        return build_error_response(500, "Failed to update confidence threshold")

    # Record audit log entry
    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="config",
        resource_id=CONFIG_KEY,
        details={
            "field_name": "confidence_threshold",
            "previous_value": previous_value,
            "new_value": new_value,
        },
    )

    return build_success_response({
        "confidence_threshold": new_value,
        "message": "Confidence threshold updated successfully",
    })
