"""Shared auth middleware used by all Lambda functions.

Checks AUTH_ENABLED environment variable:
- When 'false': skips Cognito token validation, injects hardcoded local admin user.
- When 'true': decodes JWT claims (already validated by API Gateway Cognito authorizer),
  looks up user in DynamoDB Users table, and returns user context.
"""

import base64
import json
import os

import boto3
from boto3.dynamodb.conditions import Key


class AuthError(Exception):
    """Raised when authentication or authorization fails."""

    def __init__(self, message, status_code=401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


LOCAL_ADMIN_USER = {
    "user_id": "sarah.m",
    "email": "sarah.m@greenfield.org",
    "name": "Sarah Mitchell",
    "role": "admin",
    "authorized_giveaway_years": [],
    "status": "active",
}


def _decode_jwt_payload(token):
    """Decode the payload section of a JWT without verification.

    API Gateway Cognito authorizer already validates the token,
    so we only need to extract the claims.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Invalid token format")

    payload = parts[1]
    # Add padding for base64url decoding
    padding = 4 - len(payload) % 4
    if padding != 4:
        payload += "=" * padding

    decoded = base64.urlsafe_b64decode(payload)
    return json.loads(decoded)


def _get_users_table():
    """Return a DynamoDB Table resource for the Users table."""
    table_name = os.environ.get("USERS_TABLE_NAME", "bbp-hkbg-users")
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(table_name)


def _lookup_user_by_cognito_sub(table, cognito_sub):
    """Scan for a user by cognito_sub field.

    The Users table is keyed by user_id, so we scan with a filter.
    For a small user base this is acceptable.
    """
    response = table.scan(
        FilterExpression="cognito_sub = :sub",
        ExpressionAttributeValues={":sub": cognito_sub},
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def _lookup_user_by_email(table, email):
    """Look up a user by email using the email-index GSI."""
    response = table.query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email),
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def _build_user_context(user_record):
    """Build a user context dict from a DynamoDB user record."""
    return {
        "user_id": user_record["user_id"],
        "email": user_record.get("email", ""),
        "name": user_record.get("name", ""),
        "role": user_record.get("role", ""),
        "authorized_giveaway_years": user_record.get("authorized_giveaway_years", []),
        "status": user_record.get("status", ""),
    }


def authenticate(event):
    """Authenticate the request and return a user context dict.

    Args:
        event: The Lambda event dict from API Gateway.

    Returns:
        dict with keys: user_id, email, name, role,
        authorized_giveaway_years, status.

    Raises:
        AuthError: If authentication fails or user is inactive/not found.
    """
    auth_enabled = os.environ.get("AUTH_ENABLED", "true").lower()

    if auth_enabled == "false":
        return dict(LOCAL_ADMIN_USER)

    # Extract JWT token from Authorization header
    headers = event.get("headers") or {}
    # API Gateway may normalize header keys to lowercase
    auth_header = headers.get("Authorization") or headers.get("authorization") or ""
    if not auth_header:
        raise AuthError("Missing Authorization header")

    token = auth_header
    if token.lower().startswith("bearer "):
        token = token[7:]

    if not token:
        raise AuthError("Missing token in Authorization header")

    # Decode JWT claims (already validated by API Gateway Cognito authorizer)
    try:
        claims = _decode_jwt_payload(token)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError(f"Invalid token: {exc}")

    cognito_sub = claims.get("sub", "")
    email = claims.get("email", "")

    if not cognito_sub and not email:
        raise AuthError("Token missing required claims (sub or email)")

    # Look up user in DynamoDB Users table
    table = _get_users_table()
    user_record = None

    if cognito_sub:
        user_record = _lookup_user_by_cognito_sub(table, cognito_sub)

    if not user_record and email:
        user_record = _lookup_user_by_email(table, email)

    if not user_record:
        raise AuthError("User not found", status_code=403)

    if user_record.get("status") == "inactive":
        raise AuthError("User account is inactive", status_code=403)

    return _build_user_context(user_record)
