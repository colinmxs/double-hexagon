"""Unit tests for manage_giveaway_year Lambda handler.

Requirements: 17.7, 17.8, 17.9, 17.10, 17.11
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _make_event(method="GET", body=None, path="/giveaway-years", path_params=None):
    event = {
        "httpMethod": method,
        "headers": {"Authorization": "Bearer fake"},
        "path": path,
        "pathParameters": path_params,
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _admin():
    return {"user_id": "admin-1", "email": "a@t.com", "name": "Admin", "role": "admin",
            "authorized_giveaway_years": [], "status": "active"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("CONFIG_TABLE_NAME", "test-config")
    monkeypatch.setenv("APPLICATIONS_TABLE_NAME", "test-apps")
    monkeypatch.setenv("DOCUMENTS_BUCKET_NAME", "test-docs")


MOCK_YEARS = [{"year": "2024", "status": "archived"}, {"year": "2025", "status": "active"}]


# ---- LIST ----

@patch("handler._read_active_year", return_value="2025")
@patch("handler._read_years_list", return_value=MOCK_YEARS)
@patch(AUTH_PATCH, return_value=_admin())
def test_list_years(mock_auth, mock_years, mock_active):
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body) == 2
    active_year = [y for y in body if y["is_active"]]
    assert len(active_year) == 1
    assert active_year[0]["year"] == "2025"


# ---- SET ACTIVE ----

@patch("handler.log_audit_from_context")
@patch("handler._write_active_year")
@patch("handler._read_years_list", return_value=MOCK_YEARS)
@patch("handler._write_years_list")
@patch(AUTH_PATCH, return_value=_admin())
def test_set_active_year(mock_auth, mock_write_list, mock_read_list, mock_write_active, mock_audit):
    from handler import handler
    resp = handler(_make_event("POST", {"year": "2024"}, "/giveaway-years/active"), None)
    assert resp["statusCode"] == 200
    mock_write_active.assert_called_once_with("2024")


@patch(AUTH_PATCH, return_value=_admin())
def test_set_active_missing_year(mock_auth):
    from handler import handler
    resp = handler(_make_event("POST", {}, "/giveaway-years/active"), None)
    assert resp["statusCode"] == 400


# ---- ARCHIVE ----

@patch("handler.log_audit_from_context")
@patch("handler._write_years_list")
@patch("handler._read_years_list", return_value=[{"year": "2024", "status": "active"}])
@patch("handler._get_s3_client")
@patch("handler._get_applications_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_archive_marks_read_only(mock_auth, mock_apps_table, mock_s3, mock_years, mock_write, mock_audit):
    mock_apps_table.return_value.query.return_value = {
        "Items": [{"giveaway_year": "2024", "application_id": "app-1"}]
    }
    mock_apps_table.return_value.update_item.return_value = {}
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    mock_s3.return_value.get_paginator.return_value = paginator
    from handler import handler
    resp = handler(_make_event("POST", path="/giveaway-years/2024/archive", path_params={"year": "2024"}), None)
    assert resp["statusCode"] == 200
    # Verify query uses year-index GSI
    query_kwargs = mock_apps_table.return_value.query.call_args[1]
    assert query_kwargs["IndexName"] == "year-index"
    # Verify read_only was set with single-key format
    mock_apps_table.return_value.update_item.assert_called_once()
    call_kwargs = mock_apps_table.return_value.update_item.call_args
    assert call_kwargs[1]["Key"] == {"application_id": "app-1"}
    assert call_kwargs[1]["ExpressionAttributeValues"][":ro"] is True


# ---- DELETE ----

@patch("handler.log_audit_from_context")
@patch("handler._get_config_table")
@patch("handler._write_years_list")
@patch("handler._read_years_list", return_value=[{"year": "2024", "status": "archived"}])
@patch("handler._read_active_year", return_value="2025")
@patch("handler._get_s3_client")
@patch("handler._get_applications_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_delete_removes_records(mock_auth, mock_apps_table, mock_s3, mock_active, mock_years, mock_write, mock_config, mock_audit):
    mock_apps_table.return_value.query.return_value = {
        "Items": [{"giveaway_year": "2024", "application_id": "app-1"}]
    }
    mock_apps_table.return_value.delete_item.return_value = {}
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": [{"Key": "uploads/2024/doc1.pdf"}]}]
    mock_s3.return_value.get_paginator.return_value = paginator
    mock_s3.return_value.delete_objects.return_value = {}
    from handler import handler
    resp = handler(_make_event("POST", {"confirm": True}, "/giveaway-years/2024/delete", {"year": "2024"}), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["applications_deleted"] == 1
    # Verify query uses year-index GSI
    query_kwargs = mock_apps_table.return_value.query.call_args[1]
    assert query_kwargs["IndexName"] == "year-index"
    # Verify delete uses single-key format
    mock_apps_table.return_value.delete_item.assert_called_once_with(
        Key={"application_id": "app-1"}
    )
    mock_s3.return_value.delete_objects.assert_called()


@patch(AUTH_PATCH, return_value=_admin())
def test_delete_requires_confirmation(mock_auth):
    from handler import handler
    resp = handler(_make_event("POST", {}, "/giveaway-years/2024/delete", {"year": "2024"}), None)
    assert resp["statusCode"] == 400


@patch("handler.log_audit_from_context")
@patch("handler._get_config_table")
@patch("handler._write_years_list")
@patch("handler._read_years_list", return_value=[{"year": "2024", "status": "archived"}])
@patch("handler._read_active_year", return_value="2025")
@patch("handler._get_s3_client")
@patch("handler._get_applications_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_delete_records_audit(mock_auth, mock_apps_table, mock_s3, mock_active, mock_years, mock_write, mock_config, mock_audit):
    mock_apps_table.return_value.query.return_value = {"Items": []}
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    mock_s3.return_value.get_paginator.return_value = paginator
    from handler import handler
    resp = handler(_make_event("POST", {"confirm": True}, "/giveaway-years/2024/delete", {"year": "2024"}), None)
    assert resp["statusCode"] == 200
    mock_audit.assert_called_once()
    audit_call = mock_audit.call_args
    assert audit_call[1]["action_type"] == "delete"
    assert audit_call[1]["resource_type"] == "giveaway_year"


# ---- RBAC ----

@patch(AUTH_PATCH, return_value={"user_id": "r", "email": "", "name": "", "role": "reporter", "authorized_giveaway_years": [], "status": "active"})
def test_reporter_denied(mock_auth):
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 403
