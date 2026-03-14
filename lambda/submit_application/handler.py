"""Submit Application Lambda handler.

Accepts POST requests with digital form data, validates required fields,
stores the application in DynamoDB with confidence 1.0 for all fields,
tags with the active giveaway year, sets status to "auto_approved",
and records an audit log entry.

This is a PUBLIC endpoint — no authentication required.

Requirements: 1.3, 1.4, 9.1, 17.12
"""

import logging
import os
import sys
from datetime import datetime, timezone

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from audit_middleware import log_audit_event
from utils import (
    build_error_response,
    build_success_response,
    generate_application_id,
    get_dynamodb_table,
    parse_request_body,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Required referring_agency fields
REQUIRED_AGENCY_FIELDS = ["agency_name", "contact_name", "contact_phone", "contact_email"]

# Required parent_guardian fields
REQUIRED_PARENT_FIELDS = [
    "first_name",
    "last_name",
    "address",
    "city",
    "zip_code",
    "phone",
]

# Required child fields (height_inches is mandatory per Requirement 1.3)
REQUIRED_CHILD_FIELDS = ["first_name", "last_name", "height_inches"]


def _validate_referring_agency(agency):
    """Validate referring_agency section. Returns list of error messages."""
    if not agency or not isinstance(agency, dict):
        return ["referring_agency is required and must be an object"]
    errors = []
    for field in REQUIRED_AGENCY_FIELDS:
        val = agency.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"referring_agency.{field} is required")
    return errors


def _validate_parent_guardian(parent):
    """Validate parent_guardian section. Returns list of error messages."""
    if not parent or not isinstance(parent, dict):
        return ["parent_guardian is required and must be an object"]
    errors = []
    for field in REQUIRED_PARENT_FIELDS:
        val = parent.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"parent_guardian.{field} is required")
    return errors


def _validate_children(children):
    """Validate children array. Returns list of error messages."""
    if not children or not isinstance(children, list) or len(children) == 0:
        return ["At least one child is required"]
    errors = []
    for i, child in enumerate(children):
        if not isinstance(child, dict):
            errors.append(f"children[{i}] must be an object")
            continue
        for field in REQUIRED_CHILD_FIELDS:
            val = child.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"children[{i}].{field} is required")
        # height_inches must be numeric and positive
        height = child.get("height_inches")
        if height is not None:
            try:
                h = float(height)
                if h <= 0:
                    errors.append(f"children[{i}].height_inches must be a positive number")
            except (TypeError, ValueError):
                errors.append(f"children[{i}].height_inches must be a valid number")
    return errors


def _get_active_giveaway_year():
    """Read the active giveaway year from the Config table."""
    config_table_name = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    table = get_dynamodb_table(config_table_name)
    response = table.get_item(Key={"config_key": "active_giveaway_year"})
    item = response.get("Item")
    if not item or "value" not in item:
        return None
    return str(item["value"])


def _build_field_confidence(body):
    """Build field_confidence map with 1.0 for all fields (digital submission)."""
    confidence = {}

    # Referring agency fields
    agency = body.get("referring_agency", {})
    for field in ["agency_name", "contact_name", "contact_phone", "contact_email"]:
        if agency.get(field) is not None:
            confidence[f"referring_agency.{field}"] = 1.0

    # Parent/guardian fields
    parent = body.get("parent_guardian", {})
    parent_fields = [
        "first_name", "last_name", "address", "city", "zip_code",
        "phone", "email", "primary_language", "english_speaker_in_household",
        "preferred_contact_method", "transportation_access",
    ]
    for field in parent_fields:
        if parent.get(field) is not None:
            confidence[f"parent_guardian.{field}"] = 1.0

    # Children fields
    children = body.get("children", [])
    child_fields = [
        "first_name", "last_name", "height_inches", "age", "gender",
        "bike_color_1", "bike_color_2", "knows_how_to_ride",
        "other_siblings_enrolled", "drawing_image_s3_key",
        "drawing_keywords", "dream_bike_description", "bike_number",
    ]
    for i, child in enumerate(children):
        if not isinstance(child, dict):
            continue
        for field in child_fields:
            if child.get(field) is not None:
                confidence[f"children[{i}].{field}"] = 1.0

    return confidence


def _build_children(children_input):
    """Build children array with child_id assigned to each child."""
    children = []
    for i, child in enumerate(children_input):
        if not isinstance(child, dict):
            continue
        child_record = {
            "child_id": f"child-{i + 1:03d}",
            "first_name": child.get("first_name", ""),
            "last_name": child.get("last_name", ""),
            "height_inches": child.get("height_inches"),
            "age": child.get("age"),
            "gender": child.get("gender"),
            "bike_color_1": child.get("bike_color_1"),
            "bike_color_2": child.get("bike_color_2"),
            "knows_how_to_ride": child.get("knows_how_to_ride"),
            "other_siblings_enrolled": child.get("other_siblings_enrolled"),
            "drawing_image_s3_key": child.get("drawing_image_s3_key"),
            "drawing_keywords": child.get("drawing_keywords", []),
            "dream_bike_description": child.get("dream_bike_description"),
            "bike_number": child.get("bike_number"),
        }
        # Convert height_inches to a number
        if child_record["height_inches"] is not None:
            try:
                child_record["height_inches"] = float(child_record["height_inches"])
            except (TypeError, ValueError):
                pass
        children.append(child_record)
    return children


def handler(event, context):
    """Submit a digital application form. Stores data in DynamoDB with confidence 1.0.

    Requirements: 1.3, 1.4, 9.1, 17.12
    """
    # Parse request body
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    # Validate required fields
    errors = []
    errors.extend(_validate_referring_agency(body.get("referring_agency")))
    errors.extend(_validate_parent_guardian(body.get("parent_guardian")))
    errors.extend(_validate_children(body.get("children")))

    if errors:
        return build_error_response(400, "; ".join(errors))

    # Get active giveaway year from Config table
    try:
        giveaway_year = _get_active_giveaway_year()
    except Exception:
        logger.exception("Failed to read active giveaway year from Config table")
        return build_error_response(500, "Failed to determine active giveaway year")

    if not giveaway_year:
        return build_error_response(500, "No active giveaway year configured")

    # Generate application ID and timestamp
    application_id = generate_application_id()
    now = datetime.now(timezone.utc)
    submission_timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # Build the application record
    children = _build_children(body.get("children", []))
    field_confidence = _build_field_confidence(body)

    application_record = {
        "giveaway_year": giveaway_year,
        "application_id": application_id,
        "submission_timestamp": submission_timestamp,
        "source_type": "digital",
        "status": "auto_approved",
        "overall_confidence_score": 1.0,
        "referring_agency": body.get("referring_agency", {}),
        "parent_guardian": body.get("parent_guardian", {}),
        "children": children,
        "field_confidence": field_confidence,
        "original_documents": [],
        "version": 1,
    }

    # Store in DynamoDB
    try:
        table_name = os.environ.get("APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications")
        table = get_dynamodb_table(table_name)
        table.put_item(Item=application_record)
    except Exception:
        logger.exception("Failed to store application in DynamoDB")
        return build_error_response(500, "Failed to store application")

    # Record audit log entry
    try:
        log_audit_event(
            user_id="public",
            user_name="Public Submission",
            action_type="create",
            resource_type="application",
            resource_id=application_id,
            details={"source_type": "digital", "giveaway_year": giveaway_year},
        )
    except Exception:
        # Audit log failure should not block the submission
        logger.exception("Failed to record audit log entry")

    logger.info("Application submitted: application_id=%s year=%s", application_id, giveaway_year)

    return build_success_response(
        {
            "message": "Application submitted successfully",
            "application_id": application_id,
            "giveaway_year": giveaway_year,
            "status": "auto_approved",
        },
        status_code=201,
    )
