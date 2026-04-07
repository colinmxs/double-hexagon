"""Manage Users Lambda handler.

User account CRUD, role assignment, and Cognito user management.
"""

import json


def handler(event, context):
    """Handle CRUD /api/users — manages user accounts."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "manage_users placeholder"}),
    }
