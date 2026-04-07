"""Get Application Detail Lambda handler.

Returns a single application with all fields, confidence scores, and document URLs.
"""

import json


def handler(event, context):
    """Handle GET /api/applications/{id} — returns full application detail."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "get_application_detail placeholder"}),
    }
