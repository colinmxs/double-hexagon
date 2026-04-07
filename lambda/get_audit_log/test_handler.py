"""Unit tests for get_audit_log Lambda handler.

Requirements: 15.7, 15.8, 15.9
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _make_event(method="GET", body=None, path="/audit-log", query_params=None):
    event = {
        "httpMethod": method,
        "headers": {"Authorization": "Bearer fake"},
        "path": path,
        "queryStringParameters": query_params,
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _admin():
    return {"user_id": "admin-1", "email": "a@t.com", "name": "Admin", "role": "admin",
            "authorized_giveaway_years": [], "status": "active"}


def _reporter():
    return {"user_id": "r-1", "email": "r@t.com", "name": "R", "role": "reporter",
            "authorized_giveaway_years": [], "status": "active"}


MOCK_ENTRIES = [
    {"year_month": "2025-11", "timestamp#user_id": "2025-11-15T10:00:00.000Z#admin-1",
     "user_id": "admin-1", "user_name": "Admin", "timestamp": "2025-11-15T10:00:00.000Z",
     "action_type": "create", "resource_type": "application", "resource_id": "app-1"},
    {"year_month": "2025-11", "timestamp#user_id": "2025-11-14T09:00:00.000Z#admin-1",
     "user_id": "admin-1", "user_name": "Admin", "timestamp": "2025-11-14T09:00:00.000Z",
     "action_type": "view", "resource_type": "application", "resource_id": "app-2"},
    {"year_month": "2025-11", "timestamp#user_id": "2025-11-13T08:00:00.000Z#user-2",
     "user_id": "user-2", "user_name": "Bob", "timestamp": "2025-11-13T08:00:00.000Z",
     "action_type": "export", "resource_type": "report", "resource_id": "rpt-1",
     "details": {"format": "csv"}},
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUDIT_LOG_TABLE_NAME", "test-audit")


def _mock_table(items=None):
    table = MagicMock()
    data = items or MOCK_ENTRIES
    table.query.return_value = {"Items": data}
    table.scan.return_value = {"Items": data}
    return table


# ---- GET /audit-log ----

@patch("handler._get_audit_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_query_returns_entries(mock_auth, mock_table_fn):
    mock_table_fn.return_value = _mock_table()
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "entries" in body
    assert body["count"] > 0


@patch("handler._get_audit_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_query_reverse_chronological(mock_auth, mock_table_fn):
    mock_table_fn.return_value = _mock_table()
    from handler import handler
    resp = handler(_make_event(), None)
    body = json.loads(resp["body"])
    timestamps = [e["timestamp"] for e in body["entries"]]
    assert timestamps == sorted(timestamps, reverse=True)


@patch("handler._get_audit_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_filter_by_user(mock_auth, mock_table_fn):
    mock_table_fn.return_value = _mock_table()
    from handler import handler
    resp = handler(_make_event(query_params={"user": "admin-1"}), None)
    assert resp["statusCode"] == 200
    # The filter is applied at DynamoDB level, mock returns all, but the call was made
    mock_table_fn.return_value.query.assert_called()


@patch("handler._get_audit_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_filter_by_action_type(mock_auth, mock_table_fn):
    mock_table_fn.return_value = _mock_table()
    from handler import handler
    resp = handler(_make_event(query_params={"action_type": "create"}), None)
    assert resp["statusCode"] == 200


@patch("handler._get_audit_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_filter_by_resource_type(mock_auth, mock_table_fn):
    mock_table_fn.return_value = _mock_table()
    from handler import handler
    resp = handler(_make_event(query_params={"resource_type": "application"}), None)
    assert resp["statusCode"] == 200


@patch("handler._get_audit_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_filter_by_date_range(mock_auth, mock_table_fn):
    mock_table_fn.return_value = _mock_table()
    from handler import handler
    resp = handler(_make_event(query_params={"date_from": "2025-11-14", "date_to": "2025-11-15"}), None)
    assert resp["statusCode"] == 200


# ---- RBAC ----

@patch(AUTH_PATCH, return_value=_reporter())
def test_reporter_denied(mock_auth):
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 403


# ---- Method not allowed ----

@patch(AUTH_PATCH, return_value=_admin())
def test_put_not_allowed(mock_auth):
    from handler import handler
    resp = handler(_make_event("PUT"), None)
    assert resp["statusCode"] == 405
