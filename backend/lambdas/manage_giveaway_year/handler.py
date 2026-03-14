"""Manage Giveaway Year Lambda handler.

Set active year, archive, and delete giveaway year data.
"""

import json
import os


def handler(event, context):
    """Handle POST /api/giveaway-years/* — manages giveaway year lifecycle."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": "manage_giveaway_year placeholder"}),
    }
