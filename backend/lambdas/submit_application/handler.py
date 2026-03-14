"""Submit Application Lambda handler.

Stores digital form data in DynamoDB with confidence 1.0 for all fields.
"""

import json
import os


def handler(event, context):
    """Handle POST /api/applications — stores digital form submission."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "submit_application placeholder"}),
    }
