"""Auth Me handler — returns the authenticated user's profile."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from auth_middleware import AuthError, authenticate


def handler(event, context):
    """Handle GET /api/auth/me — return current user context."""
    try:
        user_context = authenticate(event)
    except AuthError as exc:
        return {
            "statusCode": exc.status_code,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": exc.message}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({
            "user_id": user_context["user_id"],
            "email": user_context.get("email", ""),
            "name": user_context.get("name", ""),
            "role": user_context.get("role", ""),
            "authorized_giveaway_years": user_context.get("authorized_giveaway_years", []),
        }),
    }
