import json
import os


def handler(event, context):
    """Set active giveaway year, archive year data, delete year data."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "manage_giveaway_year placeholder"}),
    }
