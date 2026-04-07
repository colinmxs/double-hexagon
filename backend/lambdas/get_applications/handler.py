"""Get Applications Lambda handler.

Lists, searches, and filters applications scoped by giveaway year.
"""

import json


def handler(event, context):
    """Handle GET /api/applications — lists/searches applications."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "get_applications placeholder"}),
    }
