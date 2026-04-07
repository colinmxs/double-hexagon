"""Unit tests for manage_users Lambda handler.

Requirements: 14.2, 14.5, 14.8
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _make_event(method="GET", body=None, path="/users", path_params=None):
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


def _reporter():
    return {"user_id": "r-1", "email": "r@t.com", "name": "Reporter", "role": "reporter",
            "authorized_giveaway_years": ["2025"], "status": "active"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("USERS_TABLE_NAME", "test-users")
    monkeypatch.setenv("AUDIT_LOG_TABLE_NAME", "test-audit")
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_test")


MOCK_USERS = [
    {"user_id": "u1", "name": "Alice", "email": "alice@t.com", "role": "admin",
     "status": "active", "cognito_username": "alice@t.com"},
    {"user_id": "u2", "name": "Bob", "email": "bob@t.com", "role": "reporter",
     "status": "active", "authorized_giveaway_years": ["2025"], "cognito_username": "bob@t.com"},
]


# ---- LIST ----

@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_list_users(mock_auth, mock_table, mock_audit):
    mock_table.return_value.scan.return_value = {"Items": MOCK_USERS}
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["users"]) == 2


# ---- CREATE ----

@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch("handler._get_cognito_client")
@patch(AUTH_PATCH, return_value=_admin())
def test_create_user(mock_auth, mock_cognito, mock_table, mock_audit):
    mock_cognito.return_value.admin_create_user.return_value = {}
    mock_table.return_value.put_item.return_value = {}
    from handler import handler
    resp = handler(_make_event("POST", {"email": "new@t.com", "name": "New", "role": "reporter"}), None)
    assert resp["statusCode"] == 201
    body = json.loads(resp["body"])
    assert "user_id" in body
    mock_cognito.return_value.admin_create_user.assert_called_once()
    mock_audit.assert_called_once()


@patch(AUTH_PATCH, return_value=_admin())
def test_create_user_missing_fields(mock_auth):
    from handler import handler
    resp = handler(_make_event("POST", {"email": "x@t.com"}), None)
    assert resp["statusCode"] == 400


@patch(AUTH_PATCH, return_value=_admin())
def test_create_user_invalid_role(mock_auth):
    from handler import handler
    resp = handler(_make_event("POST", {"email": "x@t.com", "name": "X", "role": "superadmin"}), None)
    assert resp["statusCode"] == 400


@patch("handler._get_cognito_client")
@patch(AUTH_PATCH, return_value=_admin())
def test_create_user_duplicate_email(mock_auth, mock_cognito):
    from botocore.exceptions import ClientError
    mock_cognito.return_value.admin_create_user.side_effect = ClientError(
        {"Error": {"Code": "UsernameExistsException", "Message": "exists"}}, "AdminCreateUser"
    )
    from handler import handler
    resp = handler(_make_event("POST", {"email": "dup@t.com", "name": "Dup", "role": "admin"}), None)
    assert resp["statusCode"] == 409


# ---- UPDATE ----

@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_update_user_role(mock_auth, mock_table, mock_audit):
    mock_table.return_value.get_item.return_value = {"Item": MOCK_USERS[1]}
    mock_table.return_value.update_item.return_value = {}
    from handler import handler
    resp = handler(_make_event("PUT", {"role": "admin"}, "/users/u2", {"id": "u2"}), None)
    assert resp["statusCode"] == 200
    mock_table.return_value.update_item.assert_called_once()


@patch("handler._get_users_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_update_user_not_found(mock_auth, mock_table):
    mock_table.return_value.get_item.return_value = {}
    from handler import handler
    resp = handler(_make_event("PUT", {"role": "admin"}, "/users/nope", {"id": "nope"}), None)
    assert resp["statusCode"] == 404


@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch("handler._get_cognito_client")
@patch(AUTH_PATCH, return_value=_admin())
def test_update_user_password_reset(mock_auth, mock_cognito, mock_table, mock_audit):
    mock_table.return_value.get_item.return_value = {"Item": MOCK_USERS[0]}
    mock_cognito.return_value.admin_reset_user_password.return_value = {}
    from handler import handler
    resp = handler(_make_event("PUT", {"reset_password": True}, "/users/u1", {"id": "u1"}), None)
    assert resp["statusCode"] == 200
    mock_cognito.return_value.admin_reset_user_password.assert_called_once()


@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_update_giveaway_years(mock_auth, mock_table, mock_audit):
    mock_table.return_value.get_item.return_value = {"Item": MOCK_USERS[1]}
    mock_table.return_value.update_item.return_value = {}
    from handler import handler
    resp = handler(_make_event("PUT", {"authorized_giveaway_years": ["2024", "2025"]}, "/users/u2", {"id": "u2"}), None)
    assert resp["statusCode"] == 200


# ---- DISABLE ----

@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch("handler._get_cognito_client")
@patch(AUTH_PATCH, return_value=_admin())
def test_disable_user(mock_auth, mock_cognito, mock_table, mock_audit):
    mock_table.return_value.get_item.return_value = {"Item": MOCK_USERS[0]}
    mock_table.return_value.update_item.return_value = {}
    mock_cognito.return_value.admin_disable_user.return_value = {}
    from handler import handler
    resp = handler(_make_event("POST", path="/users/u1/disable", path_params={"id": "u1"}), None)
    assert resp["statusCode"] == 200
    mock_cognito.return_value.admin_disable_user.assert_called_once()
    # Verify DynamoDB status set to inactive
    call_kwargs = mock_table.return_value.update_item.call_args
    assert ":s" in call_kwargs.kwargs.get("ExpressionAttributeValues", call_kwargs[1].get("ExpressionAttributeValues", {}))


@patch("handler._get_users_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_disable_user_not_found(mock_auth, mock_table):
    mock_table.return_value.get_item.return_value = {}
    from handler import handler
    resp = handler(_make_event("POST", path="/users/nope/disable", path_params={"id": "nope"}), None)
    assert resp["statusCode"] == 404


# ---- ENABLE ----

@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch("handler._get_cognito_client")
@patch(AUTH_PATCH, return_value=_admin())
def test_enable_user(mock_auth, mock_cognito, mock_table, mock_audit):
    inactive = {**MOCK_USERS[0], "status": "inactive"}
    mock_table.return_value.get_item.return_value = {"Item": inactive}
    mock_table.return_value.update_item.return_value = {}
    mock_cognito.return_value.admin_enable_user.return_value = {}
    from handler import handler
    resp = handler(_make_event("POST", path="/users/u1/enable", path_params={"id": "u1"}), None)
    assert resp["statusCode"] == 200
    mock_cognito.return_value.admin_enable_user.assert_called_once()


# ---- DELETE ----

@patch("handler.log_audit_from_context")
@patch("handler._get_users_table")
@patch("handler._get_cognito_client")
@patch(AUTH_PATCH, return_value=_admin())
def test_delete_user(mock_auth, mock_cognito, mock_table, mock_audit):
    mock_table.return_value.get_item.return_value = {"Item": MOCK_USERS[0]}
    mock_table.return_value.delete_item.return_value = {}
    mock_cognito.return_value.admin_delete_user.return_value = {}
    from handler import handler
    resp = handler(_make_event("DELETE", path="/users/u1", path_params={"id": "u1"}), None)
    assert resp["statusCode"] == 200
    mock_cognito.return_value.admin_delete_user.assert_called_once()
    mock_table.return_value.delete_item.assert_called_once()


@patch("handler._get_users_table")
@patch(AUTH_PATCH, return_value=_admin())
def test_delete_user_not_found(mock_auth, mock_table):
    mock_table.return_value.get_item.return_value = {}
    from handler import handler
    resp = handler(_make_event("DELETE", path="/users/nope", path_params={"id": "nope"}), None)
    assert resp["statusCode"] == 404


# ---- RBAC ----

@patch(AUTH_PATCH, return_value=_reporter())
def test_reporter_denied(mock_auth):
    from handler import handler
    resp = handler(_make_event(), None)
    assert resp["statusCode"] == 403
