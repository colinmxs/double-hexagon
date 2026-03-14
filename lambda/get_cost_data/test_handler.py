"""Unit tests for get_cost_data Lambda handler.

Tests cover:
- Cost data caching (refresh at most once per day)
- Budget threshold read/update
- Budget comparison (exceeds_budget flag)
- Cost-per-application calculation
- Admin-only access enforcement

Requirements: 13.2, 13.3, 13.4, 13.5, 13.7, 13.8
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _make_event(method="GET", body=None, path="/cost-dashboard"):
    event = {
        "httpMethod": method,
        "headers": {"Authorization": "Bearer fake-token"},
        "path": path,
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _admin_context():
    return {
        "user_id": "admin-1",
        "email": "admin@test.com",
        "name": "Admin",
        "role": "admin",
        "authorized_giveaway_years": [],
        "status": "active",
    }


def _reporter_context():
    return {
        "user_id": "reporter-1",
        "email": "reporter@test.com",
        "name": "Reporter",
        "role": "reporter",
        "authorized_giveaway_years": ["2025"],
        "status": "active",
    }


MOCK_AWS_COST = {
    "service_breakdown": {"S3": 1.50, "Lambda": 3.00, "DynamoDB": 0.80},
    "trend": [
        {"month": "2025-10", "total": 4.00, "services": {"S3": 1.0, "Lambda": 2.0, "DynamoDB": 1.0}},
        {"month": "2025-11", "total": 5.30, "services": {"S3": 1.50, "Lambda": 3.00, "DynamoDB": 0.80}},
    ],
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("CONFIG_TABLE_NAME", "test-config")
    monkeypatch.setenv("APPLICATIONS_TABLE_NAME", "test-apps")


# ---- GET /cost-dashboard ----

@patch("handler._count_applications_this_month", return_value=(10, 50))
@patch("handler._read_budget", return_value=100.0)
@patch("handler._read_cache", return_value=None)
@patch("handler._write_cache")
@patch("handler._fetch_cost_from_aws", return_value=MOCK_AWS_COST)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_get_cost_data_fetches_when_no_cache(mock_auth, mock_fetch, mock_write, mock_read_cache, mock_budget, mock_apps):
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "service_breakdown" in body
    assert "trend" in body
    assert body["applications_this_month"] == 10
    assert body["applications_total"] == 50
    mock_fetch.assert_called_once()
    mock_write.assert_called_once()


@patch("handler._count_applications_this_month", return_value=(5, 20))
@patch("handler._read_budget", return_value=None)
@patch("handler._read_cache", return_value=MOCK_AWS_COST)
@patch("handler._fetch_cost_from_aws")
@patch(AUTH_PATCH, return_value=_admin_context())
def test_get_cost_data_uses_cache(mock_auth, mock_fetch, mock_read_cache, mock_budget, mock_apps):
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 200
    mock_fetch.assert_not_called()


@patch("handler._count_applications_this_month", return_value=(0, 0))
@patch("handler._read_budget", return_value=None)
@patch("handler._read_cache", return_value=MOCK_AWS_COST)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_cost_per_app_zero_when_no_apps(mock_auth, mock_cache, mock_budget, mock_apps):
    from handler import handler
    resp = handler(_make_event(), None)
    body = json.loads(resp["body"])
    assert body["cost_per_application"] == 0.0


@patch("handler._count_applications_this_month", return_value=(10, 50))
@patch("handler._read_budget", return_value=None)
@patch("handler._read_cache", return_value=MOCK_AWS_COST)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_cost_per_app_calculated(mock_auth, mock_cache, mock_budget, mock_apps):
    from handler import handler
    resp = handler(_make_event(), None)
    body = json.loads(resp["body"])
    # Last trend month total is 5.30, 10 apps => 0.53
    assert body["cost_per_application"] == 0.53


@patch("handler._count_applications_this_month", return_value=(10, 50))
@patch("handler._read_budget", return_value=3.0)
@patch("handler._read_cache", return_value=MOCK_AWS_COST)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_exceeds_budget_true(mock_auth, mock_cache, mock_budget, mock_apps):
    from handler import handler
    resp = handler(_make_event(), None)
    body = json.loads(resp["body"])
    assert body["exceeds_budget"] is True


@patch("handler._count_applications_this_month", return_value=(10, 50))
@patch("handler._read_budget", return_value=100.0)
@patch("handler._read_cache", return_value=MOCK_AWS_COST)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_exceeds_budget_false(mock_auth, mock_cache, mock_budget, mock_apps):
    from handler import handler
    resp = handler(_make_event(), None)
    body = json.loads(resp["body"])
    assert body["exceeds_budget"] is False


@patch("handler._count_applications_this_month", return_value=(10, 50))
@patch("handler._read_budget", return_value=None)
@patch("handler._read_cache", return_value=MOCK_AWS_COST)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_exceeds_budget_false_when_no_budget(mock_auth, mock_cache, mock_budget, mock_apps):
    from handler import handler
    resp = handler(_make_event(), None)
    body = json.loads(resp["body"])
    assert body["exceeds_budget"] is False


# ---- GET /cost-dashboard/budget ----

@patch("handler._read_budget", return_value=50.0)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_get_budget(mock_auth, mock_budget):
    from handler import handler
    resp = handler(_make_event(method="GET", path="/cost-dashboard/budget"), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["budget"] == 50.0


@patch("handler._read_budget", return_value=None)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_get_budget_none(mock_auth, mock_budget):
    from handler import handler
    resp = handler(_make_event(method="GET", path="/cost-dashboard/budget"), None)
    body = json.loads(resp["body"])
    assert body["budget"] is None


# ---- PUT /cost-dashboard/budget ----

@patch("handler.log_audit_from_context")
@patch("handler._write_budget")
@patch("handler._read_budget", return_value=50.0)
@patch(AUTH_PATCH, return_value=_admin_context())
def test_put_budget(mock_auth, mock_read, mock_write, mock_audit):
    from handler import handler
    resp = handler(_make_event(method="PUT", path="/cost-dashboard/budget", body={"budget": 75.0}), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["budget"] == 75.0
    mock_write.assert_called_once_with(75.0)
    mock_audit.assert_called_once()


@patch(AUTH_PATCH, return_value=_admin_context())
def test_put_budget_missing_field(mock_auth):
    from handler import handler
    resp = handler(_make_event(method="PUT", path="/cost-dashboard/budget", body={}), None)
    assert resp["statusCode"] == 400


@patch(AUTH_PATCH, return_value=_admin_context())
def test_put_budget_invalid_value(mock_auth):
    from handler import handler
    resp = handler(_make_event(method="PUT", path="/cost-dashboard/budget", body={"budget": "abc"}), None)
    assert resp["statusCode"] == 400


@patch(AUTH_PATCH, return_value=_admin_context())
def test_put_budget_negative(mock_auth):
    from handler import handler
    resp = handler(_make_event(method="PUT", path="/cost-dashboard/budget", body={"budget": -10}), None)
    assert resp["statusCode"] == 400


# ---- RBAC ----

@patch(AUTH_PATCH, return_value=_reporter_context())
def test_reporter_denied(mock_auth):
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 403


# ---- Method not allowed ----

@patch(AUTH_PATCH, return_value=_admin_context())
def test_post_not_allowed(mock_auth):
    from handler import handler
    resp = handler(_make_event(method="POST"), None)
    assert resp["statusCode"] == 405


# ---- Cache freshness ----

def test_read_cache_returns_none_when_stale():
    """Verify _read_cache returns None when cached_date != today."""
    from handler import _read_cache, _today_str
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"config_key": "cost_data_cache", "value": {"cached_date": "2020-01-01", "trend": []}}
    }
    with patch("handler._get_config_table", return_value=mock_table):
        result = _read_cache()
    assert result is None


def test_read_cache_returns_data_when_fresh():
    """Verify _read_cache returns data when cached_date == today."""
    from handler import _read_cache, _today_str
    today = _today_str()
    cached = {"cached_date": today, "trend": [{"month": "2025-11", "total": 5.0}]}
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": {"config_key": "cost_data_cache", "value": cached}}
    with patch("handler._get_config_table", return_value=mock_table):
        result = _read_cache()
    assert result is not None
    assert result["cached_date"] == today
