import json
import os


def handler(event, context):
    """Fetch cost data from AWS Cost Explorer, cached daily in DynamoDB."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "get_cost_data placeholder"}),
    }
