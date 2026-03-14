"""Cost Dashboard Lambda handler.

Routes:
- GET /cost-dashboard: Fetch cost data (cached daily in Config DynamoDB table).
- PUT /cost-dashboard/budget: Read/update monthly cost budget threshold.

Returns cost breakdown by service, 6-month trend, applications processed,
and cost-per-application.

Requirements: 13.2, 13.3, 13.4, 13.5, 13.7, 13.8
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from audit_middleware import log_audit_from_context
from rbac import require_role
from utils import (
    build_error_response,
    build_success_response,
    get_dynamodb_table,
    parse_request_body,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

COST_CACHE_KEY = "cost_data_cache"
BUDGET_KEY = "monthly_cost_budget"
SERVICES = ["Amazon Simple Storage Service", "Amazon CloudFront",
            "AWS Lambda", "Amazon API Gateway", "Amazon DynamoDB",
            "Amazon Textract", "Amazon Bedrock"]
SERVICE_SHORT = {
    "Amazon Simple Storage Service": "S3",
    "Amazon CloudFront": "CloudFront",
    "AWS Lambda": "Lambda",
    "Amazon API Gateway": "API Gateway",
    "Amazon DynamoDB": "DynamoDB",
    "Amazon Textract": "Textract",
    "Amazon Bedrock": "Bedrock",
}


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _get_config_table():
    table_name = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    return get_dynamodb_table(table_name)


def _get_applications_table():
    table_name = os.environ.get("APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications")
    return get_dynamodb_table(table_name)


def _today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_cache():
    table = _get_config_table()
    resp = table.get_item(Key={"config_key": COST_CACHE_KEY})
    item = resp.get("Item")
    if not item or "value" not in item:
        return None
    cached = item["value"] if isinstance(item["value"], dict) else json.loads(item["value"])
    if cached.get("cached_date") == _today_str():
        return cached
    return None


def _write_cache(data):
    table = _get_config_table()
    data["cached_date"] = _today_str()
    table.put_item(Item={"config_key": COST_CACHE_KEY, "value": data})


def _fetch_cost_from_aws():
    """Call AWS Cost Explorer for the last 6 months of cost data."""
    import boto3
    ce = boto3.client("ce")
    now = datetime.now(timezone.utc)
    end = now.replace(day=1).strftime("%Y-%m-%d")
    start = (now.replace(day=1) - timedelta(days=180)).replace(day=1).strftime("%Y-%m-%d")

    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    monthly = {}
    for period in resp.get("ResultsByTime", []):
        month_key = period["TimePeriod"]["Start"][:7]
        monthly[month_key] = {}
        for group in period.get("Groups", []):
            svc = group["Keys"][0]
            short = SERVICE_SHORT.get(svc)
            if short:
                monthly[month_key][short] = float(group["Metrics"]["UnblendedCost"]["Amount"])

    # Build service totals for current-ish period (last full month)
    sorted_months = sorted(monthly.keys())
    service_breakdown = {}
    for svc_short in SERVICE_SHORT.values():
        total = sum(monthly.get(m, {}).get(svc_short, 0.0) for m in sorted_months)
        service_breakdown[svc_short] = round(total, 2)

    trend = []
    for m in sorted_months:
        month_total = sum(monthly.get(m, {}).values())
        trend.append({"month": m, "total": round(month_total, 2), "services": monthly.get(m, {})})

    return {"service_breakdown": service_breakdown, "trend": trend}


def _count_applications_this_month():
    """Count applications processed in the current month."""
    table = _get_applications_table()
    now = datetime.now(timezone.utc)
    year = str(now.year)
    month_prefix = now.strftime("%Y-%m")

    try:
        resp = table.query(
            KeyConditionExpression="giveaway_year = :y",
            ExpressionAttributeValues={":y": year},
            Select="COUNT",
        )
        total = resp.get("Count", 0)
        # For current month count, filter by submission_timestamp prefix
        resp2 = table.query(
            KeyConditionExpression="giveaway_year = :y",
            FilterExpression="begins_with(submission_timestamp, :mp)",
            ExpressionAttributeValues={":y": year, ":mp": month_prefix},
            Select="COUNT",
        )
        return resp2.get("Count", 0), total
    except Exception:
        return 0, 0


def _read_budget():
    table = _get_config_table()
    resp = table.get_item(Key={"config_key": BUDGET_KEY})
    item = resp.get("Item")
    if not item or "value" not in item:
        return None
    return float(item["value"])


def _write_budget(value):
    table = _get_config_table()
    table.put_item(Item={"config_key": BUDGET_KEY, "value": str(value)})


@require_role("admin")
def handler(event, context, user_context):
    http_method = event.get("httpMethod", "GET").upper()
    path = event.get("path", "")

    if "budget" in path:
        if http_method == "GET":
            return _handle_get_budget()
        elif http_method == "PUT":
            return _handle_put_budget(event, user_context)
        return build_error_response(405, "Method not allowed")

    if http_method == "GET":
        return _handle_get_cost_data()
    return build_error_response(405, "Method not allowed")


def _handle_get_cost_data():
    """Return cost data, using daily cache."""
    cached = _read_cache()
    if cached:
        cost_data = cached
    else:
        try:
            cost_data = _fetch_cost_from_aws()
        except Exception:
            logger.exception("Failed to fetch cost data from AWS")
            return build_error_response(500, "Failed to fetch cost data")
        try:
            _write_cache(cost_data)
        except Exception:
            logger.warning("Failed to write cost cache")

    apps_this_month, apps_total = _count_applications_this_month()
    current_month_cost = 0.0
    if cost_data.get("trend"):
        current_month_cost = cost_data["trend"][-1].get("total", 0.0)

    cost_per_app = round(current_month_cost / apps_this_month, 2) if apps_this_month > 0 else 0.0

    budget = _read_budget()
    exceeds_budget = budget is not None and current_month_cost > budget

    result = {
        "service_breakdown": cost_data.get("service_breakdown", {}),
        "trend": cost_data.get("trend", []),
        "applications_this_month": apps_this_month,
        "applications_total": apps_total,
        "current_month_cost": current_month_cost,
        "cost_per_application": cost_per_app,
        "budget": budget,
        "exceeds_budget": exceeds_budget,
    }
    return build_success_response(json.loads(json.dumps(result, cls=DecimalEncoder)))


def _handle_get_budget():
    budget = _read_budget()
    return build_success_response({"budget": budget})


def _handle_put_budget(event, user_context):
    try:
        body = parse_request_body(event)
    except ValueError as exc:
        return build_error_response(400, str(exc))

    raw = body.get("budget")
    if raw is None:
        return build_error_response(400, "Missing required field: budget")

    try:
        budget = float(raw)
    except (TypeError, ValueError):
        return build_error_response(400, "Budget must be a number")

    if budget < 0:
        return build_error_response(400, "Budget must be non-negative")

    previous = _read_budget()
    _write_budget(round(budget, 2))

    log_audit_from_context(
        user_context=user_context,
        action_type="update",
        resource_type="config",
        resource_id=BUDGET_KEY,
        details={
            "field_name": "monthly_cost_budget",
            "previous_value": str(previous) if previous is not None else "none",
            "new_value": str(round(budget, 2)),
        },
    )

    return build_success_response({
        "budget": round(budget, 2),
        "message": "Budget threshold updated successfully",
    })
