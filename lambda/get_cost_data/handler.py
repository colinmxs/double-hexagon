"""Cost Dashboard Lambda handler.

GET /cost-dashboard — returns service cost breakdown and cost-per-application
for the active giveaway year, filtered to only resources tagged with
Project=bbp-hkbg.

PUT /cost-dashboard/budget — get/set monthly budget threshold.
"""

import json
import logging
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from rbac import require_role
from utils import (
    build_error_response,
    build_success_response,
    get_dynamodb_table,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

PROJECT_TAG_KEY = "Project"
PROJECT_TAG_VALUE = "bbp-hkbg"

SHORT_NAMES = {
    "Amazon Simple Storage Service": "S3",
    "Amazon CloudFront": "CloudFront",
    "AWS Lambda": "Lambda",
    "Amazon API Gateway": "API Gateway",
    "Amazon DynamoDB": "DynamoDB",
    "Amazon Cognito": "Cognito",
}

# Services that can't be tagged — costs are tracked at account level.
# These are usage-based API services with no taggable resources.
UNTAGGABLE_SERVICES = {
    "Amazon Textract": "Textract",
    "Amazon Bedrock": "Bedrock",
}


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _get_config_table():
    return get_dynamodb_table(os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config"))


def _get_applications_table():
    return get_dynamodb_table(os.environ.get("APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"))


def _get_active_giveaway_year():
    table = _get_config_table()
    resp = table.get_item(Key={"config_key": "active_giveaway_year"})
    item = resp.get("Item")
    if item and "value" in item:
        return str(item["value"])
    return None


def _count_applications(giveaway_year):
    """Count total applications for the giveaway year."""
    try:
        from boto3.dynamodb.conditions import Key

        table = _get_applications_table()
        resp = table.query(
            IndexName="year-index",
            KeyConditionExpression=Key("giveaway_year").eq(giveaway_year),
            Select="COUNT",
        )
        return resp.get("Count", 0)
    except Exception:
        logger.exception("Failed to count applications")
        return 0


def _fetch_service_costs(giveaway_year):
    """Fetch cost breakdown using two Cost Explorer queries:

    1. Tagged resources (Project=bbp-hkbg): S3, CloudFront, Lambda,
       API Gateway, DynamoDB, Cognito — these are CDK-managed and tagged.
    2. Untaggable services (Bedrock, Textract): usage-based API services
       that have no taggable resources. Tracked at account level.

    Scopes to the giveaway year (Jan 1 – Dec 31).
    """
    try:
        import boto3
        from datetime import datetime, timezone

        ce = boto3.client("ce")

        start = f"{giveaway_year}-01-01"
        now = datetime.now(timezone.utc)
        year_end = f"{giveaway_year}-12-31"
        end = min(now.strftime("%Y-%m-%d"), year_end)

        if start > end:
            return {}

        time_period = {"Start": start, "End": end}
        totals = {}

        # Query 1: Tagged resources (Project=bbp-hkbg)
        try:
            resp = ce.get_cost_and_usage(
                TimePeriod=time_period,
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                Filter={
                    "Tags": {
                        "Key": PROJECT_TAG_KEY,
                        "Values": [PROJECT_TAG_VALUE],
                    }
                },
            )
            for period in resp.get("ResultsByTime", []):
                for group in period.get("Groups", []):
                    svc = group["Keys"][0]
                    short = SHORT_NAMES.get(svc)
                    if short:
                        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                        if amount > 0.001:
                            totals[short] = round(totals.get(short, 0.0) + amount, 2)
        except Exception:
            logger.exception("Tagged cost query failed")

        # Query 2: Untaggable services (Bedrock, Textract) — account level
        try:
            resp = ce.get_cost_and_usage(
                TimePeriod=time_period,
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                Filter={
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": list(UNTAGGABLE_SERVICES.keys()),
                    }
                },
            )
            for period in resp.get("ResultsByTime", []):
                for group in period.get("Groups", []):
                    svc = group["Keys"][0]
                    short = UNTAGGABLE_SERVICES.get(svc)
                    if short:
                        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                        if amount > 0.001:
                            totals[short] = round(totals.get(short, 0.0) + amount, 2)
        except Exception:
            logger.exception("Untaggable service cost query failed")

        if totals:
            return totals

    except Exception:
        logger.exception("Cost Explorer query failed, using synthetic data")

    # No synthetic fallback — return empty if Cost Explorer fails.
    # Synthetic data would misrepresent costs for a non-profit.
    return {}


@require_role("admin")
def handler(event, context, user_context):
    """Handle GET /cost-dashboard and PUT /cost-dashboard/budget."""
    method = event.get("httpMethod", "GET")
    path = event.get("path", "")

    # PUT /cost-dashboard/budget
    if method == "PUT" and "budget" in path:
        return _handle_budget_put(event)

    # GET /cost-dashboard
    giveaway_year = _get_active_giveaway_year()
    if not giveaway_year:
        return build_error_response(500, "No active giveaway year configured")

    services = _fetch_service_costs(giveaway_year)
    total_cost = round(sum(services.values()), 2)
    apps_total = _count_applications(giveaway_year)
    cost_per_app = round(total_cost / max(apps_total, 1), 2)

    result = {
        "giveaway_year": giveaway_year,
        "service_breakdown": services,
        "total_cost": total_cost,
        "applications_total": apps_total,
        "cost_per_application": cost_per_app,
    }
    return build_success_response(
        json.loads(json.dumps(result, cls=_DecimalEncoder))
    )


def _handle_budget_put(event):
    """Store monthly budget threshold in config table."""
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return build_error_response(400, "Invalid JSON body")

    budget = body.get("budget")
    if budget is None:
        return build_error_response(400, "budget field is required")

    try:
        budget_val = float(budget)
    except (TypeError, ValueError):
        return build_error_response(400, "budget must be a valid number")

    if budget_val < 0:
        return build_error_response(400, "budget must be non-negative")

    table = _get_config_table()
    table.put_item(Item={
        "config_key": "monthly_budget",
        "value": Decimal(str(round(budget_val, 2))),
    })

    return build_success_response({"budget": budget_val})
