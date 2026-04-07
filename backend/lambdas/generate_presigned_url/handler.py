"""Generate Pre-signed URL Lambda handler.

Returns a pre-signed S3 upload URL with 15-minute expiry.
"""

import json


def handler(event, context):
    """Handle POST /api/uploads/presign — returns pre-signed S3 PUT URL."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "generate_presigned_url placeholder"}),
    }
