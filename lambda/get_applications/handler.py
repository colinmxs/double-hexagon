"""Get Applications Lambda handler.

Lists, searches, and filters applications scoped by giveaway year.
Supports pagination, status filtering, and search by family name or agency name.
Enforces giveaway year scoping for reporter role.

Requirements: 5.1, 5.2, 5.3, 14.6, 17.3
"""

import base64
import json
import logging
import os
import sys
from decimal import Decimal

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from rbac import enforce_year_scoping, require_role
from utils import (
    build_error_response,
    build_success_response,
    generate_presigned_get_url,
    get_dynamodb_table,
    get_query_parameter,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that converts Decimal to int or float."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def _get_active_giveaway_year():
    """Read the active giveaway year from the Config table."""
    config_table_name = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    table = get_dynamodb_table(config_table_name)
    response = table.get_item(Key={"config_key": "active_giveaway_year"})
    item = response.get("Item")
    if not item or "value" not in item:
        return None
    return str(item["value"])


def _decode_next_token(token_str):
    """Decode a base64-encoded pagination token to a DynamoDB ExclusiveStartKey."""
    try:
        decoded = base64.b64decode(token_str)
        return json.loads(decoded)
    except Exception:
        return None


def _encode_next_token(last_evaluated_key):
    """Encode a DynamoDB LastEvaluatedKey as a base64 pagination token."""
    if not last_evaluated_key:
        return None
    raw = json.dumps(last_evaluated_key, cls=DecimalEncoder)
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def _get_drawing_thumbnail_url(application):
    """Get a pre-signed URL for the first child's drawing image if it exists."""
    bucket = os.environ.get("DOCUMENTS_BUCKET", "")
    if not bucket:
        return None

    children = application.get("children", [])
    if not children:
        return None

    for child in children:
        s3_key = child.get("drawing_image_s3_key")
        if s3_key:
            try:
                return generate_presigned_get_url(bucket, s3_key)
            except Exception:
                logger.warning("Failed to generate presigned URL for drawing")
                return None
    return None


def _convert_decimal(value):
    """Convert Decimal values to int or float for JSON serialization."""
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return value


def _format_application(application):
    """Format an application record for the list response."""
    parent = application.get("parent_guardian", {})
    family_name = parent.get("last_name", "")

    item = {
        "application_id": application.get("application_id", ""),
        "family_name": family_name,
        "submission_timestamp": application.get("submission_timestamp", ""),
        "source_type": application.get("source_type", ""),
        "status": application.get("status", ""),
        "overall_confidence_score": _convert_decimal(
            application.get("overall_confidence_score")
        ),
        "drawing_thumbnail_url": _get_drawing_thumbnail_url(application),
    }
    return item


def _matches_search(application, search_term):
    """Check if an application matches the search term (family name or agency name)."""
    search_lower = search_term.lower()

    # Search by family name (parent_guardian.last_name)
    parent = application.get("parent_guardian", {})
    last_name = parent.get("last_name", "")
    if last_name and search_lower in last_name.lower():
        return True

    # Search by agency name (referring_agency.agency_name)
    agency = application.get("referring_agency", {})
    agency_name = agency.get("agency_name", "")
    if agency_name and search_lower in agency_name.lower():
        return True

    return False


def _query_by_status(table, giveaway_year, status, page_size, exclusive_start_key=None):
    """Query applications using the status-index GSI."""
    from boto3.dynamodb.conditions import Key

    kwargs = {
        "IndexName": "status-index",
        "KeyConditionExpression": Key("giveaway_year").eq(giveaway_year)
        & Key("status").eq(status),
        "Limit": page_size,
    }
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key

    response = table.query(**kwargs)
    return response


def _query_all(table, giveaway_year, page_size, exclusive_start_key=None):
    """Query all applications for a giveaway year."""
    from boto3.dynamodb.conditions import Key

    kwargs = {
        "KeyConditionExpression": Key("giveaway_year").eq(giveaway_year),
        "Limit": page_size,
    }
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key

    response = table.query(**kwargs)
    return response


@require_role("admin", "reporter")
def handler(event, context, user_context):
    """List applications with optional filters, search, and pagination.

    Query params:
        giveaway_year: Year to query (defaults to active year from Config)
        status: Optional status filter
        search: Optional search term (family name or agency name)
        page_size: Number of results per page (default 50, max 200)
        next_token: Base64-encoded pagination token

    Requirements: 5.1, 5.2, 5.3, 14.6, 17.3
    """
    # Parse query parameters
    giveaway_year = get_query_parameter(event, "giveaway_year")
    status_filter = get_query_parameter(event, "status")
    search_term = get_query_parameter(event, "search")
    next_token = get_query_parameter(event, "next_token")

    # Parse page_size
    page_size_str = get_query_parameter(event, "page_size")
    if page_size_str:
        try:
            page_size = int(page_size_str)
            page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        except (TypeError, ValueError):
            page_size = DEFAULT_PAGE_SIZE
    else:
        page_size = DEFAULT_PAGE_SIZE

    # Default to active giveaway year if not specified
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

    # Decode pagination token
    exclusive_start_key = None
    if next_token:
        exclusive_start_key = _decode_next_token(next_token)
        if exclusive_start_key is None:
            return build_error_response(400, "Invalid pagination token")

    # Query DynamoDB
    try:
        table_name = os.environ.get(
            "APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"
        )
        table = get_dynamodb_table(table_name)

        if status_filter:
            response = _query_by_status(
                table, giveaway_year, status_filter, page_size, exclusive_start_key
            )
        else:
            response = _query_all(
                table, giveaway_year, page_size, exclusive_start_key
            )
    except Exception:
        logger.exception("Failed to query applications")
        return build_error_response(500, "Failed to retrieve applications")

    items = response.get("Items", [])
    last_evaluated_key = response.get("LastEvaluatedKey")

    # Apply search filter client-side (DynamoDB doesn't support contains on nested attrs in key conditions)
    if search_term:
        items = [app for app in items if _matches_search(app, search_term)]

    # Format response items
    formatted = [_format_application(app) for app in items]

    # Build response
    result = {
        "applications": formatted,
        "count": len(formatted),
        "giveaway_year": giveaway_year,
    }

    # Encode pagination token
    encoded_token = _encode_next_token(last_evaluated_key)
    if encoded_token:
        result["next_token"] = encoded_token

    return build_success_response(result)
