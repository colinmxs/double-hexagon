import json
import os


def handler(event, context):
    """Generate a pre-signed S3 upload URL with 15-minute expiry."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "generate_presigned_url placeholder"}),
    }
