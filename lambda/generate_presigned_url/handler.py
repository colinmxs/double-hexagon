"""Generate Pre-signed URL Lambda handler.

Accepts POST requests with file metadata (name, type, size),
validates file type (PDF, PNG, JPEG) and size (≤10MB),
generates a pre-signed S3 PUT URL with 15-minute expiry,
and returns the pre-signed URL with a reference identifier.

This is a PUBLIC endpoint (rate-limited) — no auth middleware needed.

Requirements: 2.1, 2.2, 2.3, 2.7, 16.9
"""

import logging
import os
import sys

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from utils import (
    build_error_response,
    build_success_response,
    generate_application_id,
    generate_presigned_url,
    get_dynamodb_table,
    parse_request_body,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Allowed MIME types (Requirement 2.1)
ALLOWED_FILE_TYPES = {"application/pdf", "image/png", "image/jpeg"}

# Max file size: 10MB (Requirement 2.2)
MAX_FILE_SIZE = 10 * 1024 * 1024


def _get_active_giveaway_year():
    """Read the active giveaway year from the Config table."""
    config_table_name = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    table = get_dynamodb_table(config_table_name)
    response = table.get_item(Key={"config_key": "active_giveaway_year"})
    item = response.get("Item")
    if not item or "value" not in item:
        return None
    return str(item["value"])


def handler(event, context):
    """Generate a pre-signed S3 upload URL with 15-minute expiry.

    Requirements: 2.1, 2.2, 2.3, 2.7, 16.9
    """
    # Parse request body
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    # Extract file metadata
    file_name = body.get("file_name")
    file_type = body.get("file_type")
    file_size = body.get("file_size")

    # Validate required fields
    if not file_name or not isinstance(file_name, str) or not file_name.strip():
        return build_error_response(400, "file_name is required")

    if not file_type or not isinstance(file_type, str) or not file_type.strip():
        return build_error_response(400, "file_type is required")

    if file_size is None:
        return build_error_response(400, "file_size is required")

    # Validate file type (Requirement 2.1)
    if file_type not in ALLOWED_FILE_TYPES:
        return build_error_response(
            400,
            f"Unsupported file type. Accepted formats: PDF, PNG, JPEG",
        )

    # Validate file size (Requirement 2.2, 2.7)
    try:
        file_size_int = int(file_size)
    except (TypeError, ValueError):
        return build_error_response(400, "file_size must be a valid number")

    if file_size_int <= 0:
        return build_error_response(400, "file_size must be greater than zero")

    if file_size_int > MAX_FILE_SIZE:
        return build_error_response(
            400,
            f"File exceeds maximum size of 10MB",
        )

    # Get active giveaway year from Config table
    try:
        giveaway_year = _get_active_giveaway_year()
    except Exception:
        logger.exception("Failed to read active giveaway year from Config table")
        return build_error_response(500, "Failed to determine active giveaway year")

    if not giveaway_year:
        return build_error_response(500, "No active giveaway year configured")

    # Generate a reference identifier
    reference_id = generate_application_id()

    # Build the S3 key: uploads/{giveaway_year}/{reference_id}/{filename}
    sanitized_name = file_name.strip().replace(" ", "_")
    s3_key = f"uploads/{giveaway_year}/{reference_id}/{sanitized_name}"

    # Generate pre-signed PUT URL with 15-minute expiry (Requirement 16.9)
    bucket_name = os.environ.get("DOCUMENTS_BUCKET", "bbp-hkbg-documents")
    try:
        presigned_url = generate_presigned_url(bucket_name, s3_key, content_type=file_type, expiry_seconds=900)
    except Exception:
        logger.exception("Failed to generate pre-signed URL")
        return build_error_response(500, "Failed to generate upload URL")

    logger.info(
        "Pre-signed URL generated: reference_id=%s year=%s",
        reference_id,
        giveaway_year,
    )

    return build_success_response(
        {
            "upload_url": presigned_url,
            "reference_id": reference_id,
            "s3_key": s3_key,
        },
        status_code=200,
    )
