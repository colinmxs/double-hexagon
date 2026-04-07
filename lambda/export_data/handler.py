"""Export Data Lambda handler.

Generates CSV exports: Bike Build List or Family Contact List.
Supports status filtering and records audit log entries for export actions.

POST endpoint. Request body:
{
    "export_type": "bike_build_list" | "family_contact_list",
    "giveaway_year": "2025" (optional, defaults to active year),
    "status_filter": "manually_approved" (optional)
}

Requirements: 6.1, 6.2, 6.3, 6.5, 10.5, 15.5
"""

import csv
import io
import logging
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
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

VALID_EXPORT_TYPES = ("bike_build_list", "family_contact_list")

BIKE_BUILD_HEADERS = [
    "Child First Name",
    "Child Last Name",
    "Height (inches)",
    "Age",
    "Gender",
    "Bike Color 1",
    "Bike Color 2",
    "Knows How to Ride",
    "Dream Bike Description",
    "Drawing Keywords",
    "Bike Number",
]

FAMILY_CONTACT_HEADERS = [
    "Parent/Guardian First Name",
    "Last Name",
    "Phone",
    "Email",
    "Address",
    "City",
    "Zip Code",
    "Primary Language",
    "Preferred Contact Method",
    "Transportation Access",
    "Referring Agency Name",
]


def _get_active_giveaway_year():
    """Read the active giveaway year from the Config table."""
    config_table_name = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    table = get_dynamodb_table(config_table_name)
    response = table.get_item(Key={"config_key": "active_giveaway_year"})
    item = response.get("Item")
    if not item or "value" not in item:
        return None
    return str(item["value"])


def _convert_decimal(value):
    """Convert Decimal values to int or float for CSV output."""
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return value


def _query_applications(table, giveaway_year, status_filter=None):
    """Query all matching applications, handling pagination internally.

    Uses status-index GSI when status_filter is provided, otherwise queries
    the main table by giveaway_year partition key.
    """
    from boto3.dynamodb.conditions import Key

    all_items = []
    kwargs = {}

    if status_filter:
        kwargs = {
            "IndexName": "status-index",
            "KeyConditionExpression": Key("giveaway_year").eq(giveaway_year)
            & Key("status").eq(status_filter),
        }
    else:
        kwargs = {
            "IndexName": "year-index",
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


def _format_drawing_keywords(keywords):
    """Join drawing keywords as a semicolon-separated string."""
    if not keywords:
        return ""
    if isinstance(keywords, list):
        return ";".join(str(k) for k in keywords)
    return str(keywords)


def _generate_bike_build_csv(applications):
    """Generate Bike Build List CSV content.

    One row per child across all applications.
    Columns: Child First Name, Child Last Name, Height (inches), Age, Gender,
    Bike Color 1, Bike Color 2, Knows How to Ride, Dream Bike Description,
    Drawing Keywords, Bike Number

    Requirements: 6.1, 10.5
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(BIKE_BUILD_HEADERS)

    for app in applications:
        children = app.get("children", [])
        for child in children:
            height = _convert_decimal(child.get("height_inches", ""))
            age = _convert_decimal(child.get("age", ""))
            knows_ride = child.get("knows_how_to_ride", "")
            if isinstance(knows_ride, bool):
                knows_ride = "Yes" if knows_ride else "No"

            writer.writerow([
                child.get("first_name", ""),
                child.get("last_name", ""),
                height,
                age,
                child.get("gender", ""),
                child.get("bike_color_1", ""),
                child.get("bike_color_2", ""),
                knows_ride,
                child.get("dream_bike_description", ""),
                _format_drawing_keywords(child.get("drawing_keywords")),
                child.get("bike_number", ""),
            ])

    return output.getvalue()


def _generate_family_contact_csv(applications):
    """Generate Family Contact List CSV content.

    One row per application.
    Columns: Parent/Guardian First Name, Last Name, Phone, Email, Address,
    City, Zip Code, Primary Language, Preferred Contact Method,
    Transportation Access, Referring Agency Name

    Requirement: 6.2
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(FAMILY_CONTACT_HEADERS)

    for app in applications:
        parent = app.get("parent_guardian", {})
        agency = app.get("referring_agency", {})
        transport = parent.get("transportation_access", "")
        if isinstance(transport, bool):
            transport = "Yes" if transport else "No"

        writer.writerow([
            parent.get("first_name", ""),
            parent.get("last_name", ""),
            parent.get("phone", ""),
            parent.get("email", ""),
            parent.get("address", ""),
            parent.get("city", ""),
            parent.get("zip_code", ""),
            parent.get("primary_language", ""),
            parent.get("preferred_contact_method", ""),
            transport,
            agency.get("agency_name", ""),
        ])

    return output.getvalue()


@require_role("admin", "reporter")
def handler(event, context, user_context):
    """Generate CSV export: bike build list or family contact list.

    Requirements: 6.1, 6.2, 6.3, 6.5, 10.5, 15.5
    """
    # Parse request body
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    export_type = body.get("export_type")
    if not export_type or export_type not in VALID_EXPORT_TYPES:
        return build_error_response(
            400,
            f"Invalid export_type. Must be one of: {', '.join(VALID_EXPORT_TYPES)}",
        )

    giveaway_year = body.get("giveaway_year")
    status_filter = body.get("status_filter")

    # Default to active giveaway year if not provided
    if not giveaway_year:
        try:
            giveaway_year = _get_active_giveaway_year()
        except Exception:
            logger.exception("Failed to read active giveaway year")
            return build_error_response(500, "Failed to determine active giveaway year")
        if not giveaway_year:
            return build_error_response(500, "No active giveaway year configured")

    # Enforce year scoping for reporter role (Requirement 14.6)
    if not enforce_year_scoping(user_context, giveaway_year):
        return build_error_response(
            403, "Forbidden: not authorized for this giveaway year"
        )

    # Query applications from DynamoDB
    try:
        table_name = os.environ.get(
            "APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"
        )
        table = get_dynamodb_table(table_name)
        applications = _query_applications(table, giveaway_year, status_filter)
    except Exception:
        logger.exception("Failed to query applications for export")
        return build_error_response(500, "Failed to retrieve applications for export")

    # Generate CSV
    if export_type == "bike_build_list":
        csv_content = _generate_bike_build_csv(applications)
    else:
        csv_content = _generate_family_contact_csv(applications)

    # Record audit log entry (Requirement 15.5)
    audit_details = {
        "export_type": export_type,
        "giveaway_year": giveaway_year,
    }
    if status_filter:
        audit_details["status_filter"] = status_filter

    log_audit_from_context(
        user_context=user_context,
        action_type="export",
        resource_type="application",
        resource_id=f"export_{export_type}_{giveaway_year}",
        details=audit_details,
    )

    return build_success_response({
        "csv_content": csv_content,
        "export_type": export_type,
        "giveaway_year": giveaway_year,
        "record_count": len(applications),
        "content_type": "text/csv",
    })
