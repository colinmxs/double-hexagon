"""Access Management Lambda handler.

Routes:
- GET    /users           — List all users
- POST   /users           — Create user (Cognito + DynamoDB)
- PUT    /users/{id}      — Update user (role, authorized years)
- DELETE /users/{id}      — Delete user (Cognito + DynamoDB)
- POST   /users/{id}/disable — Deactivate user
- POST   /users/{id}/enable  — Enable user

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.7, 14.8, 14.9, 15.1
"""

import logging
import os
import sys
import uuid

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

VALID_ROLES = ("admin", "reporter", "submitter")


def _get_users_table():
    table_name = os.environ.get("USERS_TABLE_NAME", "bbp-hkbg-users")
    return get_dynamodb_table(table_name)


def _get_cognito_client():
    return boto3.client("cognito-idp")


def _get_user_pool_id():
    return os.environ.get("USER_POOL_ID", "")


@require_role("admin")
def handler(event, context, user_context):
    method = event.get("httpMethod", "GET").upper()
    path = event.get("path", "")
    user_id = get_path_parameter(event, "id")

    if path.endswith("/disable") and method == "POST":
        return _handle_disable(user_id, user_context)
    if path.endswith("/enable") and method == "POST":
        return _handle_enable(user_id, user_context)
    if method == "GET" and not user_id:
        return _handle_list()
    if method == "POST" and not user_id:
        return _handle_create(event, user_context)
    if method == "PUT" and user_id:
        return _handle_update(event, user_id, user_context)
    if method == "DELETE" and user_id:
        return _handle_delete(user_id, user_context)

    return build_error_response(405, "Method not allowed")


def _handle_list():
    table = _get_users_table()
    resp = table.scan()
    users = resp.get("Items", [])
    result = []
    for u in users:
        result.append({
            "user_id": u["user_id"],
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "role": u.get("role", ""),
            "authorized_giveaway_years": u.get("authorized_giveaway_years", []),
            "status": u.get("status", "active"),
            "last_login": u.get("last_login", ""),
        })
    return build_success_response({"users": result})


def _handle_create(event, user_context):
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    email = body.get("email", "").strip()
    name = body.get("name", "").strip()
    role = body.get("role", "").strip()

    if not email or not name or not role:
        return build_error_response(400, "Missing required fields: email, name, role")
    if role not in VALID_ROLES:
        return build_error_response(400, f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    user_id = str(uuid.uuid4())
    pool_id = _get_user_pool_id()
    cognito = _get_cognito_client()

    # Create in Cognito
    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": name},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "UsernameExistsException":
            return build_error_response(409, "A user with this email already exists")
        logger.exception("Cognito create user failed")
        return build_error_response(500, "Failed to create user in identity provider")

    # Create in DynamoDB
    table = _get_users_table()
    item = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "role": role,
        "authorized_giveaway_years": body.get("authorized_giveaway_years", []),
        "status": "active",
        "cognito_username": email,
    }
    table.put_item(Item=item)

    log_audit_from_context(
        user_context=user_context,
        action_type="create",
        resource_type="user_account",
        resource_id=user_id,
        details={"role": role},
    )

    return build_success_response({"user_id": user_id, "message": "User created"}, 201)


def _handle_update(event, user_id, user_context):
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    table = _get_users_table()
    resp = table.get_item(Key={"user_id": user_id})
    existing = resp.get("Item")
    if not existing:
        return build_error_response(404, "User not found")

    updates = {}
    details = {}

    if "role" in body:
        new_role = body["role"]
        if new_role not in VALID_ROLES:
            return build_error_response(400, f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
        details["previous_role"] = existing.get("role", "")
        details["new_role"] = new_role
        updates["role"] = new_role

    if "authorized_giveaway_years" in body:
        updates["authorized_giveaway_years"] = body["authorized_giveaway_years"]

    if "name" in body:
        updates["name"] = body["name"]

    # Handle password reset trigger
    if body.get("reset_password"):
        pool_id = _get_user_pool_id()
        cognito = _get_cognito_client()
        username = existing.get("cognito_username") or existing.get("email", "")
        try:
            cognito.admin_reset_user_password(UserPoolId=pool_id, Username=username)
            details["password_reset"] = "triggered"
        except ClientError:
            logger.exception("Password reset failed")
            return build_error_response(500, "Failed to trigger password reset")

    if updates:
        expr_parts = []
        attr_names = {}
        attr_values = {}
        for i, (k, v) in enumerate(updates.items()):
            placeholder = f"#k{i}"
            val_placeholder = f":v{i}"
            expr_parts.append(f"{placeholder} = {val_placeholder}")
            attr_names[placeholder] = k
            attr_values[val_placeholder] = v
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )

    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="user_account",
        resource_id=user_id,
        details=details if details else {"fields_updated": list(updates.keys())},
    )

    return build_success_response({"message": "User updated"})


def _handle_disable(user_id, user_context):
    table = _get_users_table()
    resp = table.get_item(Key={"user_id": user_id})
    existing = resp.get("Item")
    if not existing:
        return build_error_response(404, "User not found")

    pool_id = _get_user_pool_id()
    cognito = _get_cognito_client()
    username = existing.get("cognito_username") or existing.get("email", "")

    try:
        cognito.admin_disable_user(UserPoolId=pool_id, Username=username)
    except ClientError:
        logger.exception("Cognito disable user failed")
        return build_error_response(500, "Failed to disable user in identity provider")

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "inactive"},
    )

    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="user_account",
        resource_id=user_id,
        details={"action": "deactivate", "previous_status": existing.get("status", "active")},
    )

    return build_success_response({"message": "User deactivated"})


def _handle_enable(user_id, user_context):
    table = _get_users_table()
    resp = table.get_item(Key={"user_id": user_id})
    existing = resp.get("Item")
    if not existing:
        return build_error_response(404, "User not found")

    pool_id = _get_user_pool_id()
    cognito = _get_cognito_client()
    username = existing.get("cognito_username") or existing.get("email", "")

    try:
        cognito.admin_enable_user(UserPoolId=pool_id, Username=username)
    except ClientError:
        logger.exception("Cognito enable user failed")
        return build_error_response(500, "Failed to enable user in identity provider")

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "active"},
    )

    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="user_account",
        resource_id=user_id,
        details={"action": "enable", "previous_status": existing.get("status", "inactive")},
    )

    return build_success_response({"message": "User enabled"})


def _handle_delete(user_id, user_context):
    table = _get_users_table()
    resp = table.get_item(Key={"user_id": user_id})
    existing = resp.get("Item")
    if not existing:
        return build_error_response(404, "User not found")

    pool_id = _get_user_pool_id()
    cognito = _get_cognito_client()
    username = existing.get("cognito_username") or existing.get("email", "")

    try:
        cognito.admin_delete_user(UserPoolId=pool_id, Username=username)
    except ClientError:
        logger.exception("Cognito delete user failed")
        return build_error_response(500, "Failed to delete user from identity provider")

    table.delete_item(Key={"user_id": user_id})

    log_audit_from_context(
        user_context=user_context,
        action_type="delete",
        resource_type="user_account",
        resource_id=user_id,
    )

    return build_success_response({"message": "User deleted"})
