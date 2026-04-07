"""Shared RBAC (Role-Based Access Control) module for Lambda functions.

Provides:
- require_role(*allowed_roles): Decorator that authenticates the request,
  checks the user's role, and passes user_context to the handler.
- enforce_year_scoping(user_context, requested_year): Checks whether a user
  is authorized to access data for a specific giveaway year.
- build_error_response(status_code, message): Builds an API Gateway proxy
  response with JSON body and CORS headers.

Works with auth_middleware.authenticate() from Task 6.1.

Requirements: 14.3, 14.6, 14.10
"""

import functools
import json
import os

try:
    from shared.auth_middleware import AuthError, authenticate
except ImportError:
    from auth_middleware import AuthError, authenticate


ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:4173",
).split(",")


def _get_cors_headers(origin=None):
    """Return CORS headers, reflecting the request origin if it is allowed."""
    if "*" in ALLOWED_ORIGINS:
        allow_origin = "*"
    elif origin and origin in ALLOWED_ORIGINS:
        allow_origin = origin
    else:
        allow_origin = ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else ""
    return {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Vary": "Origin",
    }


CORS_HEADERS = _get_cors_headers()


def build_error_response(status_code, message, event=None):
    """Build an API Gateway proxy response with JSON body and CORS headers.

    Error messages must never contain PII (Requirement 16.10).

    Args:
        status_code: HTTP status code (e.g. 403, 401, 500).
        message: A safe, generic error message with no PII.
        event: Optional API Gateway event to extract Origin header from.

    Returns:
        dict: API Gateway proxy response.
    """
    origin = None
    if event:
        headers = event.get("headers") or {}
        origin = headers.get("origin") or headers.get("Origin")
    return {
        "statusCode": status_code,
        "headers": {**_get_cors_headers(origin), "Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def enforce_year_scoping(user_context, requested_year):
    """Check whether a user is authorized to access a specific giveaway year.

    Rules (Requirement 14.6):
    - admin: always allowed (full access).
    - reporter: allowed only if requested_year is in their
      authorized_giveaway_years list.
    - submitter: always denied (no admin/report access).

    Args:
        user_context: Dict returned by authenticate(), must contain 'role'
            and 'authorized_giveaway_years'.
        requested_year: The giveaway year string to check (e.g. "2025").

    Returns:
        True if the user may access data for that year, False otherwise.
    """
    role = user_context.get("role", "")

    if role == "admin":
        return True

    if role == "reporter":
        authorized_years = user_context.get("authorized_giveaway_years", [])
        return str(requested_year) in [str(y) for y in authorized_years]

    # submitter or any unknown role — no admin access
    return False


def require_role(*allowed_roles):
    """Decorator that enforces authentication and role-based access control.

    Usage::

        @require_role("admin")
        def handler(event, context, user_context):
            ...

        @require_role("admin", "reporter")
        def handler(event, context, user_context):
            ...

    The decorator:
    1. Calls authenticate(event) to get user_context.
    2. If authentication fails, returns the appropriate error response.
    3. Checks that user_context["role"] is in *allowed_roles*.
    4. If the role is not allowed, returns a 403 response (Requirement 14.10).
    5. Otherwise, calls the wrapped handler with user_context as a third arg.

    Args:
        *allowed_roles: One or more role strings (e.g. "admin", "reporter").

    Returns:
        A decorator that wraps a Lambda handler function.
    """

    def decorator(handler):
        @functools.wraps(handler)
        def wrapper(event, context):
            # Step 1: Authenticate
            try:
                user_context = authenticate(event)
            except AuthError as exc:
                return build_error_response(exc.status_code, exc.message)

            # Step 2: Check role
            user_role = user_context.get("role", "")
            if user_role not in allowed_roles:
                return build_error_response(
                    403, "Forbidden: insufficient permissions"
                )

            # Step 3: Invoke handler with user_context
            return handler(event, context, user_context)

        return wrapper

    return decorator
