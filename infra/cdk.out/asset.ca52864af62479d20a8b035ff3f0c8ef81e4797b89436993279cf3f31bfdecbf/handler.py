import json
import os


def handler(event, context):
    """Generate CSV exports: bike build list or family contact list."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "export_data placeholder"}),
    }
