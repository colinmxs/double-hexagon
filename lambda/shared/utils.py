"""Shared backend utilities for all Lambda functions.

Provides:
- CORS_HEADERS: Standard CORS headers dict for API Gateway responses.
- get_dynamodb_table(table_name): Returns a boto3 DynamoDB Table resource.
- generate_presigned_url(bucket, key, expiry): Pre-signed S3 PUT URL (15-min default).
- generate_presigned_get_url(bucket, key, expiry): Pre-signed S3 GET URL (15-min default).
- generate_application_id(): ULID-like unique ID using time + uuid.
- build_success_response(body, status_code): API Gateway success response with CORS.
- build_error_response(status_code, message): API Gateway error response, no PII.
- parse_request_body(event): Safely parse JSON body from API Gateway event.
- get_path_parameter(event, param_name): Extract path parameter from event.
- get_query_parameter(event, param_name, default): Extract query string parameter.

Requirements: 9.4, 16.9, 16.10
"""

import json
import logging
import os
import time
import uuid

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


def get_dynamodb_table(table_name):
    """Return a boto3 DynamoDB Table resource.

    Args:
        table_name: Name of the DynamoDB table.

    Returns:
        boto3 DynamoDB Table resource.
    """
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def generate_presigned_url(bucket_name, object_key, expiry_seconds=900):
    """Generate a pre-signed S3 PUT URL for file uploads.

    Default expiry is 15 minutes (900 seconds) per Requirement 16.9.

    Args:
        bucket_name: S3 bucket name.
        object_key: S3 object key.
        expiry_seconds: URL expiry in seconds (default 900 = 15 minutes).

    Returns:
        str: Pre-signed PUT URL.
    """
    s3_client = boto3.client("s3")
    url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket_name, "Key": object_key},
        ExpiresIn=expiry_seconds,
    )
    return url


def generate_presigned_get_url(bucket_name, object_key, expiry_seconds=900):
    """Generate a pre-signed S3 GET URL for file downloads.

    Default expiry is 15 minutes (900 seconds).

    Args:
        bucket_name: S3 bucket name.
        object_key: S3 object key.
        expiry_seconds: URL expiry in seconds (default 900 = 15 minutes).

    Returns:
        str: Pre-signed GET URL.
    """
    s3_client = boto3.client("s3")
    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": object_key},
        ExpiresIn=expiry_seconds,
    )
    return url


def generate_application_id():
    """Generate a ULID-like unique application ID.

    Combines a millisecond timestamp prefix with a UUID suffix to produce
    a time-sortable, unique identifier. No external library required.

    Returns:
        str: A unique ID string like "01JXXXXXXXXXX-<uuid4-hex>".
    """
    # Millisecond timestamp encoded as zero-padded hex (10 chars covers ~35 years)
    timestamp_ms = int(time.time() * 1000)
    time_part = format(timestamp_ms, "012x").upper()
    # Random component from uuid4
    random_part = uuid.uuid4().hex[:16].upper()
    return f"{time_part}{random_part}"


def build_success_response(body, status_code=200):
    """Build an API Gateway proxy success response with JSON body and CORS headers.

    Args:
        body: Dict or list to serialize as JSON response body.
        status_code: HTTP status code (default 200).

    Returns:
        dict: API Gateway proxy response.
    """
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def build_error_response(status_code, message):
    """Build an API Gateway proxy error response with CORS headers.

    Error messages must NEVER contain PII (Requirement 16.10).

    Args:
        status_code: HTTP status code (e.g. 400, 404, 500).
        message: A safe, generic error message with no PII.

    Returns:
        dict: API Gateway proxy response.
    """
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def parse_request_body(event):
    """Safely parse JSON body from an API Gateway proxy event.

    Handles both raw and base64-encoded bodies.

    Args:
        event: API Gateway Lambda proxy event dict.

    Returns:
        dict: Parsed JSON body.

    Raises:
        ValueError: If the body is missing, empty, or not valid JSON.
    """
    body = event.get("body")
    if not body:
        raise ValueError("Request body is missing or empty")

    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Invalid JSON in request body") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")

    return parsed


def get_path_parameter(event, param_name):
    """Extract a path parameter from an API Gateway proxy event.

    Args:
        event: API Gateway Lambda proxy event dict.
        param_name: Name of the path parameter (e.g. "id").

    Returns:
        str or None: The parameter value, or None if not present.
    """
    path_params = event.get("pathParameters") or {}
    return path_params.get(param_name)


def get_query_parameter(event, param_name, default=None):
    """Extract a query string parameter from an API Gateway proxy event.

    Args:
        event: API Gateway Lambda proxy event dict.
        param_name: Name of the query parameter.
        default: Default value if the parameter is not present.

    Returns:
        str or default: The parameter value, or default if not present.
    """
    query_params = event.get("queryStringParameters") or {}
    return query_params.get(param_name, default)
