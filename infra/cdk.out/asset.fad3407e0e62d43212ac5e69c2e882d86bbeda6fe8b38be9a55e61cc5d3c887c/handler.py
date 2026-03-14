import json
import os


def handler(event, context):
    """Return single application with all fields, confidence scores, and document URLs."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "get_application_detail placeholder"}),
    }
