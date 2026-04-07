"""Export Data Lambda handler.

Generates CSV exports (bike build list or family contact list).
"""

import json


def handler(event, context):
    """Handle POST /api/exports/* — generates CSV export."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "export_data placeholder"}),
    }
