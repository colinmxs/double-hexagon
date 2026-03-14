"""Get Application Detail Lambda handler.

Returns a single application record with all fields, per-field confidence scores,
pre-signed URLs for original documents and drawing images.
Records an audit log entry for the view action.

Requirements: 5.4, 5.6, 9.1, 9.2, 15.2
"""

import logging
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from audit_middleware import log_audit_from_context
from rbac import require_role
from utils import (
    build_error_response,
    build_success_response,
    generate_presigned_get_url,
    get_dynamodb_table,
    get_path_parameter,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _convert_decimals(obj):
    """Recursively convert Decimal values to int or float for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj


def _enrich_with_presigned_urls(application, bucket):
    """Add pre-signed GET URLs for original documents and drawing images.

    Mutates the application dict in place, adding 'presigned_url' to each
    original document entry and 'drawing_image_url' to each child record.
    """
    if not bucket:
        return

    # Original documents
    for doc in application.get("original_documents", []):
        s3_key = doc.get("s3_key")
        if s3_key:
            try:
                doc["presigned_url"] = generate_presigned_get_url(bucket, s3_key)
            except Exception:
                logger.warning("Failed to generate presigned URL for document: %s", s3_key)
                doc["presigned_url"] = None

    # Child drawing images
    for child in application.get("children", []):
        s3_key = child.get("drawing_image_s3_key")
        if s3_key:
            try:
                child["drawing_image_url"] = generate_presigned_get_url(bucket, s3_key)
            except Exception:
                logger.warning("Failed to generate presigned URL for drawing: %s", s3_key)
                child["drawing_image_url"] = None


@require_role("admin")
def handler(event, context, user_context):
    """Return full application record with confidence scores and document URLs.

    Path parameters:
        giveaway_year: The giveaway year partition key.
        application_id: The application sort key (ULID).

    Requirements: 5.4, 5.6, 9.1, 9.2, 15.2
    """
    giveaway_year = get_path_parameter(event, "giveaway_year")
    application_id = get_path_parameter(event, "application_id")

    if not giveaway_year or not application_id:
        return build_error_response(400, "Missing required path parameters: giveaway_year and application_id")

    # Fetch application from DynamoDB
    try:
        table_name = os.environ.get("APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications")
        table = get_dynamodb_table(table_name)
        response = table.get_item(
            Key={"giveaway_year": giveaway_year, "application_id": application_id}
        )
    except Exception:
        logger.exception("Failed to fetch application")
        return build_error_response(500, "Failed to retrieve application")

    item = response.get("Item")
    if not item:
        return build_error_response(404, "Application not found")

    # Generate pre-signed URLs for documents and drawings
    bucket = os.environ.get("DOCUMENTS_BUCKET", "")
    _enrich_with_presigned_urls(item, bucket)

    # Record audit log entry for view action (Requirement 15.2)
    try:
        log_audit_from_context(
            user_context=user_context,
            action_type="view",
            resource_type="application",
            resource_id=application_id,
        )
    except Exception:
        logger.warning("Failed to record audit log for view action on %s", application_id)

    # Convert Decimals and return full record
    application = _convert_decimals(item)

    return build_success_response({"application": application})
