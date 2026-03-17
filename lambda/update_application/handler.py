"""Update Application Lambda handler.

Accepts PUT requests to update application fields, status, and children data.
Sets edited field confidence to 1.0, retains previous version in S3 for audit,
and records audit log entries with field-level change details.

Only admin role can update applications.

Requirements: 5.7, 5.8, 5.9, 5.10, 5.11, 9.2, 15.3
"""

import json
import logging
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

import boto3
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


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that converts Decimal to int or float."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def _convert_decimals(obj):
    """Recursively convert Decimal values to int or float for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj


def _get_s3_client():
    """Return a boto3 S3 client."""
    return boto3.client("s3")


def _save_version_to_s3(bucket, giveaway_year, application_id, version, record):
    """Save the current application version to S3 for audit (Requirement 9.2).

    Stores at: versions/{giveaway_year}/{application_id}/v{version}.json
    """
    s3_key = f"versions/{giveaway_year}/{application_id}/v{version}.json"
    s3_client = _get_s3_client()
    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=json.dumps(_convert_decimals(record), cls=DecimalEncoder),
        ContentType="application/json",
    )
    return s3_key


import re

_ARRAY_KEY_RE = re.compile(r"^(\w+)\[(\d+)]$")


def _resolve_key(obj, key):
    """Resolve a single path segment, handling both dict keys and array indices like 'children[0]'."""
    m = _ARRAY_KEY_RE.match(key)
    if m:
        arr_name, idx = m.group(1), int(m.group(2))
        arr = obj.get(arr_name) if isinstance(obj, dict) else None
        if isinstance(arr, list) and 0 <= idx < len(arr):
            return arr[idx]
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return None


def _get_nested_value(obj, field_path):
    """Get a value from a nested dict using dot-notation path.

    Supports paths like 'parent_guardian.phone', 'referring_agency.agency_name',
    and array-indexed paths like 'children[0].first_name'.
    """
    keys = field_path.split(".")
    current = obj
    for key in keys:
        current = _resolve_key(current, key)
        if current is None:
            return None
    return current


def _set_nested_value(obj, field_path, value):
    """Set a value in a nested dict using dot-notation path.

    Supports array-indexed paths like 'children[0].first_name'.
    Creates intermediate dicts if they don't exist (but not arrays).
    """
    keys = field_path.split(".")
    current = obj
    for key in keys[:-1]:
        m = _ARRAY_KEY_RE.match(key)
        if m:
            arr_name, idx = m.group(1), int(m.group(2))
            arr = current.get(arr_name) if isinstance(current, dict) else None
            if isinstance(arr, list) and 0 <= idx < len(arr):
                current = arr[idx]
            else:
                return  # can't navigate into missing array element
        else:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
    # Set the final key
    last = keys[-1]
    m = _ARRAY_KEY_RE.match(last)
    if m:
        arr_name, idx = m.group(1), int(m.group(2))
        arr = current.get(arr_name) if isinstance(current, dict) else None
        if isinstance(arr, list) and 0 <= idx < len(arr):
            arr[idx] = value
    else:
        current[last] = value


def _apply_field_updates(application, field_updates, field_confidence):
    """Apply field updates and set confidence to 1.0 for each edited field.

    Returns a list of audit detail dicts for each changed field.
    """
    audit_changes = []
    for field_path, new_value in field_updates.items():
        previous_value = _get_nested_value(application, field_path)
        _set_nested_value(application, field_path, new_value)
        field_confidence[field_path] = Decimal("1.0")
        audit_changes.append({
            "field_name": field_path,
            "previous_value": str(previous_value) if previous_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
        })
    return audit_changes


def _apply_status_update(application, new_status):
    """Apply a status update and return audit detail."""
    previous_status = application.get("status")
    application["status"] = new_status
    return {
        "field_name": "status",
        "previous_value": str(previous_status) if previous_status is not None else None,
        "new_value": str(new_status),
    }


def _apply_children_updates(application, children_updates, field_confidence):
    """Apply updates to children records by child_id.

    Supports updating bike_number, drawing_keywords, dream_bike_description,
    and any other child fields. Sets confidence to 1.0 for edited child fields.

    Returns a list of audit detail dicts and a list of child_ids not found.
    """
    children = application.get("children", [])
    children_by_id = {}
    children_index = {}
    for idx, child in enumerate(children):
        cid = child.get("child_id")
        if cid:
            children_by_id[cid] = child
            children_index[cid] = idx

    audit_changes = []
    not_found = []

    for update in children_updates:
        child_id = update.get("child_id")
        if not child_id or child_id not in children_by_id:
            not_found.append(child_id)
            continue

        child = children_by_id[child_id]
        idx = children_index[child_id]

        for field_name, new_value in update.items():
            if field_name == "child_id":
                continue
            previous_value = child.get(field_name)
            child[field_name] = new_value
            confidence_key = f"children[{idx}].{field_name}"
            field_confidence[confidence_key] = Decimal("1.0")
            audit_changes.append({
                "field_name": f"children.{child_id}.{field_name}",
                "previous_value": str(previous_value) if previous_value is not None else None,
                "new_value": str(new_value) if new_value is not None else None,
            })

    return audit_changes, not_found


@require_role("admin")
def handler(event, context, user_context):
    """Update application fields, status, or children data.

    Path parameters:
        giveaway_year: The giveaway year partition key.
        application_id: The application sort key (ULID).

    Request body (all optional):
        field_updates: dict of field paths to new values
        status: new status value (e.g. "manually_approved")
        children_updates: array of child update objects with child_id

    Requirements: 5.7, 5.8, 5.9, 5.10, 5.11, 9.2, 15.3
    """
    giveaway_year = get_path_parameter(event, "giveaway_year")
    application_id = get_path_parameter(event, "application_id")

    if not giveaway_year or not application_id:
        return build_error_response(400, "Missing required path parameters: giveaway_year and application_id")

    # Parse request body
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    field_updates = body.get("field_updates", {})
    status_update = body.get("status")
    children_updates = body.get("children_updates", [])

    if not field_updates and not status_update and not children_updates:
        return build_error_response(400, "No updates provided")

    # Fetch current application from DynamoDB
    table_name = os.environ.get("APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications")
    try:
        table = get_dynamodb_table(table_name)
        response = table.get_item(
            Key={"giveaway_year": giveaway_year, "application_id": application_id}
        )
    except Exception:
        logger.exception("Failed to fetch application")
        return build_error_response(500, "Failed to retrieve application")

    application = response.get("Item")
    if not application:
        return build_error_response(404, "Application not found")

    # Save current version to S3 before making changes (Requirement 9.2)
    bucket = os.environ.get("DOCUMENTS_BUCKET", "")
    current_version = int(application.get("version", 1))

    if bucket:
        try:
            s3_key = _save_version_to_s3(
                bucket, giveaway_year, application_id, current_version, application
            )
            application["previous_versions_s3_key"] = s3_key
        except Exception:
            logger.exception("Failed to save version to S3")
            return build_error_response(500, "Failed to save previous version")
    

    # Collect all audit changes
    all_audit_changes = []
    field_confidence = application.get("field_confidence", {})

    # Apply field updates (Requirement 5.7)
    if field_updates:
        changes = _apply_field_updates(application, field_updates, field_confidence)
        all_audit_changes.extend(changes)

    # Apply status update (Requirement 5.8)
    if status_update:
        change = _apply_status_update(application, status_update)
        all_audit_changes.append(change)

    # Apply children updates - bike_number (5.10), drawing_keywords (5.9, 5.11)
    if children_updates:
        changes, not_found = _apply_children_updates(
            application, children_updates, field_confidence
        )
        all_audit_changes.extend(changes)

    # Increment version
    application["version"] = current_version + 1
    application["field_confidence"] = field_confidence

    # Write updated record back to DynamoDB
    try:
        table.put_item(Item=application)
    except Exception:
        logger.exception("Failed to update application in DynamoDB")
        return build_error_response(500, "Failed to update application")

    # Record audit log entries (Requirement 15.3)
    try:
        log_audit_from_context(
            user_context=user_context,
            action_type="update",
            resource_type="application",
            resource_id=application_id,
            details={"changes": all_audit_changes},
        )
    except Exception:
        logger.warning("Failed to record audit log for update on %s", application_id)

    logger.info(
        "Application updated: application_id=%s year=%s version=%d",
        application_id,
        giveaway_year,
        application["version"],
    )

    return build_success_response({"application": _convert_decimals(application)})
