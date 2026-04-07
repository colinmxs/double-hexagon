"""Local development API server.

Translates Flask HTTP requests into API Gateway Lambda proxy events,
calls the real Lambda handlers, and returns the responses.

Zero changes to handler code required — this is a pure adapter layer.

Usage:
    pip install flask flask-cors
    AUTH_ENABLED=false python lambda/local_api.py

Runs on http://localhost:8000 by default.
"""

import importlib
import os
import sys

# Ensure shared module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))

# --- Moto mock toggle: must run BEFORE any boto3 imports ---
from local_mock import is_moto_enabled, start_moto

if is_moto_enabled():
    start_moto()

from flask import Flask, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Force local dev mode (skip Cognito auth, use hardcoded admin user)
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("DOCUMENTS_BUCKET", "bbp-hkbg-documents")


# ---------------------------------------------------------------------------
# Event translation: Flask request → API Gateway Lambda proxy event
# ---------------------------------------------------------------------------

def _build_event(path_params=None, resource_path=None):
    """Build an API Gateway proxy integration event from the current Flask request."""
    body = request.get_data(as_text=True) or None

    headers = dict(request.headers)
    query_params = dict(request.args) if request.args else None

    return {
        "httpMethod": request.method,
        "path": request.path,
        "headers": headers,
        "queryStringParameters": query_params,
        "pathParameters": path_params,
        "body": body,
        "isBase64Encoded": False,
        "resource": resource_path or request.path,
        "requestContext": {},
    }


def _flask_response(lambda_result):
    """Convert a Lambda handler response dict into a Flask response tuple."""
    status = lambda_result.get("statusCode", 200)
    resp_headers = lambda_result.get("headers", {})
    body = lambda_result.get("body", "")
    return body, status, resp_headers


# ---------------------------------------------------------------------------
# Handler loader (lazy import, cached)
# ---------------------------------------------------------------------------

_handler_cache = {}


def _get_handler(module_name, handler_attr="handler"):
    """Import and cache a handler function from lambda/<module_name>/handler.py."""
    cache_key = f"{module_name}.{handler_attr}"
    if cache_key not in _handler_cache:
        mod = importlib.import_module(f"{module_name}.handler")
        _handler_cache[cache_key] = getattr(mod, handler_attr)
    return _handler_cache[cache_key]


# ---------------------------------------------------------------------------
# Route definitions — mirrors API Gateway routes from api-stack.ts
# ---------------------------------------------------------------------------

# --- Public endpoints (no auth) ---

@app.route("/api/applications", methods=["POST"])
def submit_application():
    event = _build_event()
    result = _get_handler("submit_application")(event, None)
    return _flask_response(result)


@app.route("/api/uploads/presign", methods=["POST"])
def generate_presigned_url():
    event = _build_event()
    result = _get_handler("generate_presigned_url")(event, None)
    return _flask_response(result)


# --- Auth ---

@app.route("/api/auth/me", methods=["GET"])
def get_auth_me():
    event = _build_event()
    result = _get_handler("get_auth_me")(event, None)
    return _flask_response(result)


# --- Applications ---

@app.route("/api/applications", methods=["GET"])
def get_applications():
    event = _build_event()
    result = _get_handler("get_applications")(event, None)
    return _flask_response(result)


@app.route("/api/applications/<application_id>", methods=["GET"])
def get_application_detail(application_id):
    event = _build_event(
        path_params={"application_id": application_id},
    )
    result = _get_handler("get_application_detail")(event, None)
    return _flask_response(result)


@app.route("/api/applications/<application_id>", methods=["PUT"])
def update_application(application_id):
    event = _build_event(
        path_params={"application_id": application_id},
    )
    result = _get_handler("update_application")(event, None)
    return _flask_response(result)


@app.route("/api/applications/<application_id>/status", methods=["PUT"])
def update_application_status(application_id):
    event = _build_event(
        path_params={"application_id": application_id},
    )
    result = _get_handler("update_application")(event, None)
    return _flask_response(result)


@app.route("/api/applications/<application_id>/children/<child_id>/bike-number", methods=["PUT"])
def update_child_bike_number(application_id, child_id):
    event = _build_event(
        path_params={"application_id": application_id, "child_id": child_id},
    )
    result = _get_handler("update_application")(event, None)
    return _flask_response(result)


@app.route("/api/applications/<application_id>/children/<child_id>/drawing-keywords", methods=["PUT"])
def update_child_drawing_keywords(application_id, child_id):
    event = _build_event(
        path_params={"application_id": application_id, "child_id": child_id},
    )
    result = _get_handler("update_application")(event, None)
    return _flask_response(result)


# --- Exports ---

@app.route("/api/exports/bike-build-list", methods=["POST"])
@app.route("/api/exports/family-contact-list", methods=["POST"])
def export_data():
    event = _build_event()
    result = _get_handler("export_data")(event, None)
    return _flask_response(result)


# --- Reports ---

@app.route("/api/reports/saved", methods=["GET", "POST"])
def manage_reports_collection():
    event = _build_event()
    result = _get_handler("manage_reports")(event, None)
    return _flask_response(result)


@app.route("/api/reports/saved/<report_id>", methods=["GET", "PUT", "DELETE"])
def manage_reports_item(report_id):
    event = _build_event(path_params={"id": report_id})
    result = _get_handler("manage_reports")(event, None)
    return _flask_response(result)


@app.route("/api/reports/run", methods=["POST"])
def run_report():
    event = _build_event()
    result = _get_handler("run_report")(event, None)
    return _flask_response(result)


@app.route("/api/reports/export", methods=["POST"])
def export_report():
    event = _build_event()
    result = _get_handler("run_report", handler_attr="export_handler")(event, None)
    return _flask_response(result)


# --- Cost Dashboard ---

@app.route("/api/cost-dashboard", methods=["GET"])
def get_cost_data():
    event = _build_event()
    result = _get_handler("get_cost_data")(event, None)
    return _flask_response(result)


# --- Users ---

@app.route("/api/users", methods=["GET", "POST"])
def manage_users_collection():
    event = _build_event()
    result = _get_handler("manage_users")(event, None)
    return _flask_response(result)


@app.route("/api/users/<user_id>", methods=["PUT", "DELETE"])
def manage_users_item(user_id):
    event = _build_event(path_params={"id": user_id})
    result = _get_handler("manage_users")(event, None)
    return _flask_response(result)


@app.route("/api/users/<user_id>/disable", methods=["POST"])
def disable_user(user_id):
    event = _build_event(path_params={"id": user_id})
    result = _get_handler("manage_users")(event, None)
    return _flask_response(result)


@app.route("/api/users/<user_id>/enable", methods=["POST"])
def enable_user(user_id):
    event = _build_event(path_params={"id": user_id})
    result = _get_handler("manage_users")(event, None)
    return _flask_response(result)


# --- Audit Log ---

@app.route("/api/audit-log", methods=["GET"])
def get_audit_log():
    event = _build_event()
    result = _get_handler("get_audit_log")(event, None)
    return _flask_response(result)


@app.route("/api/audit-log/export", methods=["POST"])
def export_audit_log():
    event = _build_event()
    result = _get_handler("get_audit_log")(event, None)
    return _flask_response(result)


# --- Giveaway Years ---

@app.route("/api/giveaway-years", methods=["GET"])
def list_giveaway_years():
    event = _build_event()
    result = _get_handler("manage_giveaway_year")(event, None)
    return _flask_response(result)


@app.route("/api/giveaway-years/active", methods=["POST"])
def set_active_year():
    event = _build_event()
    result = _get_handler("manage_giveaway_year")(event, None)
    return _flask_response(result)


@app.route("/api/giveaway-years/<year>/archive", methods=["POST"])
def archive_year(year):
    event = _build_event(path_params={"year": year})
    result = _get_handler("manage_giveaway_year")(event, None)
    return _flask_response(result)


@app.route("/api/giveaway-years/<year>/unarchive", methods=["POST"])
def unarchive_year(year):
    event = _build_event(path_params={"year": year})
    result = _get_handler("manage_giveaway_year")(event, None)
    return _flask_response(result)


@app.route("/api/giveaway-years/<year>/delete", methods=["POST"])
def delete_year(year):
    event = _build_event(path_params={"year": year})
    result = _get_handler("manage_giveaway_year")(event, None)
    return _flask_response(result)


# --- Confidence Threshold ---

@app.route("/api/confidence-threshold", methods=["GET", "PUT"])
def confidence_threshold():
    event = _build_event()
    result = _get_handler("get_confidence_threshold")(event, None)
    return _flask_response(result)


# --- Image serving (drawings + documents from S3) ---

@app.route("/api/drawings/<path:key>", methods=["GET"])
def serve_drawing(key):
    import boto3
    try:
        s3 = boto3.client("s3", region_name="us-east-1")
        obj = s3.get_object(Bucket=os.environ.get("DOCUMENTS_BUCKET", "bbp-hkbg-documents"), Key=key)
        body = obj["Body"].read()
        content_type = obj.get("ContentType", "image/png")
        return body, 200, {"Content-Type": content_type, "Cache-Control": "max-age=3600"}
    except Exception:
        return "Not found", 404


@app.route("/api/documents/<path:key>", methods=["GET"])
def serve_document(key):
    import boto3
    try:
        s3 = boto3.client("s3", region_name="us-east-1")
        obj = s3.get_object(Bucket=os.environ.get("DOCUMENTS_BUCKET", "bbp-hkbg-documents"), Key=key)
        body = obj["Body"].read()
        content_type = obj.get("ContentType", "application/octet-stream")
        return body, 200, {"Content-Type": content_type, "Cache-Control": "max-age=3600"}
    except Exception:
        return "Not found", 404


# ---------------------------------------------------------------------------
# OPTIONS handler for CORS preflight (catch-all)
# ---------------------------------------------------------------------------

@app.route("/api/<path:path>", methods=["OPTIONS"])
def options_handler(path):
    return "", 200, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Local API server running on http://localhost:{port}")
    print("AUTH_ENABLED =", os.environ.get("AUTH_ENABLED", "true"))
    app.run(host="0.0.0.0", port=port, debug=True)
