"""Giveaway Year Lifecycle Lambda handler.

Routes:
- GET  /giveaway-years                — List giveaway years
- POST /giveaway-years/active         — Set active giveaway year
- POST /giveaway-years/{year}/archive   — Archive a year (reversible)
- POST /giveaway-years/{year}/unarchive — Unarchive a year
- POST /giveaway-years/{year}/delete    — Delete a year (permanent)

Requirements: 17.1, 17.2, 17.6, 17.7, 17.8, 17.9, 17.10, 17.11
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

import boto3
from botocore.exceptions import ClientError

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

ACTIVE_YEAR_KEY = "active_giveaway_year"
GIVEAWAY_YEARS_KEY = "giveaway_years"


def _get_config_table():
    return get_dynamodb_table(os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config"))


def _get_applications_table():
    return get_dynamodb_table(os.environ.get("APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"))


def _get_bucket_name():
    return os.environ.get("DOCUMENTS_BUCKET_NAME", "bbp-hkbg-documents")


def _get_s3_client():
    return boto3.client("s3")


def _read_years_list():
    table = _get_config_table()
    resp = table.get_item(Key={"config_key": GIVEAWAY_YEARS_KEY})
    item = resp.get("Item")
    if not item or "value" not in item:
        return []
    val = item["value"]
    if isinstance(val, str):
        return json.loads(val)
    return val


def _write_years_list(years):
    table = _get_config_table()
    table.put_item(Item={"config_key": GIVEAWAY_YEARS_KEY, "value": years})


def _read_active_year():
    table = _get_config_table()
    resp = table.get_item(Key={"config_key": ACTIVE_YEAR_KEY})
    item = resp.get("Item")
    if not item or "value" not in item:
        return None
    return str(item["value"])


def _write_active_year(year):
    table = _get_config_table()
    table.put_item(Item={"config_key": ACTIVE_YEAR_KEY, "value": year})


@require_role("admin")
def handler(event, context, user_context):
    method = event.get("httpMethod", "GET").upper()
    path = event.get("path", "")
    year = get_path_parameter(event, "year")

    if path.endswith("/active") and method == "POST":
        return _handle_set_active(event, user_context)
    if path.endswith("/archive") and method == "POST" and year:
        return _handle_archive(year, user_context)
    if path.endswith("/unarchive") and method == "POST" and year:
        return _handle_unarchive(year, user_context)
    if path.endswith("/delete") and method == "POST" and year:
        return _handle_delete(event, year, user_context)
    if method == "GET":
        return _handle_list()

    return build_error_response(405, "Method not allowed")


def _handle_list():
    years = _read_years_list()
    active = _read_active_year()
    result = []
    for y in years:
        if isinstance(y, dict):
            y["is_active"] = y.get("year") == active
            result.append(y)
        else:
            result.append({"year": str(y), "is_active": str(y) == active, "status": "active"})
    return build_success_response(result)


def _handle_set_active(event, user_context):
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    year = body.get("year")
    if not year:
        return build_error_response(400, "Missing required field: year")

    year = str(year)
    years = _read_years_list()
    year_strs = [str(y["year"]) if isinstance(y, dict) else str(y) for y in years]

    # Auto-create year if not in list
    if year not in year_strs:
        years.append({"year": year, "status": "active"})
        _write_years_list(years)

    _write_active_year(year)

    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="giveaway_year",
        resource_id=year,
        details={"action": "set_active"},
    )

    return build_success_response({"message": f"Active year set to {year}", "year": year})


def _handle_archive(year, user_context):
    # Mark applications as read-only
    table = _get_applications_table()
    resp = table.query(
        IndexName="year-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("giveaway_year").eq(year),
    )
    items = resp.get("Items", [])
    for item in items:
        table.update_item(
            Key={"application_id": item["application_id"]},
            UpdateExpression="SET #ro = :ro",
            ExpressionAttributeNames={"#ro": "read_only"},
            ExpressionAttributeValues={":ro": True},
        )

    # Update year status (S3 lifecycle rules handle Glacier transition automatically)
    years = _read_years_list()
    for y in years:
        if isinstance(y, dict) and str(y.get("year")) == year:
            y["status"] = "archived"
        elif str(y) == year:
            idx = years.index(y)
            years[idx] = {"year": year, "status": "archived"}
    _write_years_list(years)

    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="giveaway_year",
        resource_id=year,
        details={"action": "archive", "applications_archived": len(items)},
    )

    return build_success_response({"message": f"Year {year} archived", "applications_archived": len(items)})


def _handle_unarchive(year, user_context):
    # Remove read-only flag from applications
    table = _get_applications_table()
    resp = table.query(
        IndexName="year-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("giveaway_year").eq(year),
    )
    items = resp.get("Items", [])
    for item in items:
        table.update_item(
            Key={"application_id": item["application_id"]},
            UpdateExpression="REMOVE #ro",
            ExpressionAttributeNames={"#ro": "read_only"},
        )

    # Update year status back to active
    years = _read_years_list()
    for y in years:
        if isinstance(y, dict) and str(y.get("year")) == year:
            y["status"] = "active"
    _write_years_list(years)

    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="giveaway_year",
        resource_id=year,
        details={"action": "unarchive", "applications_restored": len(items)},
    )

    return build_success_response({"message": f"Year {year} unarchived", "applications_restored": len(items)})


def _handle_delete(event, year, user_context):
    try:
        body = parse_request_body(event)
    except ValueError:
        body = {}

    if not body.get("confirm"):
        return build_error_response(400, "Deletion requires confirmation. Set confirm: true.")

    # Delete all DynamoDB application records
    table = _get_applications_table()
    resp = table.query(
        IndexName="year-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("giveaway_year").eq(year),
    )
    items = resp.get("Items", [])
    for item in items:
        table.delete_item(Key={"application_id": item["application_id"]})

    # Delete all S3 objects
    s3 = _get_s3_client()
    bucket = _get_bucket_name()
    deleted_objects = 0
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=f"uploads/{year}/"):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
                deleted_objects += len(objects)
        # Also delete drawings and versions
        for prefix in [f"drawings/{year}/", f"versions/{year}/"]:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
                    deleted_objects += len(objects)
    except ClientError:
        logger.exception("Failed to delete S3 objects")

    # Remove from years list
    years = _read_years_list()
    years = [y for y in years if (str(y.get("year")) if isinstance(y, dict) else str(y)) != year]
    _write_years_list(years)

    # If active year was deleted, clear it
    active = _read_active_year()
    if active == year:
        _get_config_table().delete_item(Key={"config_key": ACTIVE_YEAR_KEY})

    log_audit_from_context(
        user_context=user_context,
        action_type="delete",
        resource_type="giveaway_year",
        resource_id=year,
        details={"applications_deleted": len(items), "s3_objects_deleted": deleted_objects},
    )

    return build_success_response({
        "message": f"Year {year} permanently deleted",
        "applications_deleted": len(items),
        "s3_objects_deleted": deleted_objects,
    })
