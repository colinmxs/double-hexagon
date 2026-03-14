"""Get Cost Data Lambda handler.

Fetches cost data from AWS Cost Explorer (cached daily in DynamoDB).
"""

import json
import os


def handler(event, context):
    """Handle GET /api/cost-dashboard — returns cost data."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "get_cost_data placeholder"}),
    }
