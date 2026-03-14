"""Unit tests for get_confidence_threshold Lambda handler.

Tests cover:
- GET returns current threshold from Config table
- GET returns default 0.80 when not set
- PUT updates threshold with valid value
- PUT validates value is between 0.0 and 1.0
- PUT records audit log entry
- Admin-only access enforcement
- Error handling

Requirements: 4.5
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _make_event(method="GET", body=None):
    """Build an API Gateway proxy event."""
    event = {
        "httpMethod": method,
        "headers": {"Authorization": "Bearer fake-token"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _admin_context():
    return {
        "user_id": "admin-001",
        "email": "admin@test.com",
        "name": "Admin User",
        "role": "admin",
        "authorized_giveaway_years": [],
        "status": "active",
    }


class TestGetThreshold:
    """Tests for GET confidence threshold."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_get_returns_stored_threshold(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"config_key": "confidence_threshold", "value": "0.75"}
        }
        mock_table_fn.return_value = mock_table

        from handler import handler

        response = handler(_make_event("GET"), {})
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["confidence_threshold"] == "0.75"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_get_returns_default_when_not_set(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table_fn.return_value = mock_table

        from handler import handler

        response = handler(_make_event("GET"), {})
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["confidence_threshold"] == "0.80"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_get_returns_default_when_item_has_no_value(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"config_key": "confidence_threshold"}
        }
        mock_table_fn.return_value = mock_table

        from handler import handler

        response = handler(_make_event("GET"), {})
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["confidence_threshold"] == "0.80"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_get_handles_dynamodb_error(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB error")
        mock_table_fn.return_value = mock_table

        from handler import handler

        response = handler(_make_event("GET"), {})

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Failed to read" in body["error"]


class TestPutThreshold:
    """Tests for PUT confidence threshold."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler._get_config_table")
    def test_put_updates_threshold(self, mock_table_fn, mock_audit, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"config_key": "confidence_threshold", "value": "0.80"}
        }
        mock_table_fn.return_value = mock_table

        from handler import handler

        response = handler(_make_event("PUT", {"value": 0.75}), {})
        body = json.loads(response["body"])

        assert response["statusCode"] == 200
        assert body["confidence_threshold"] == "0.75"
        mock_table.put_item.assert_called_once_with(
            Item={"config_key": "confidence_threshold", "value": "0.75"}
        )

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler._get_config_table")
    def test_put_records_audit_log(self, mock_table_fn, mock_audit, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"config_key": "confidence_threshold", "value": "0.80"}
        }
        mock_table_fn.return_value = mock_table

        from handler import handler

        handler(_make_event("PUT", {"value": 0.65}), {})

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["action_type"] == "update"
        assert call_kwargs["resource_type"] == "config"
        assert call_kwargs["resource_id"] == "confidence_threshold"
        assert call_kwargs["details"]["previous_value"] == "0.80"
        assert call_kwargs["details"]["new_value"] == "0.65"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_put_accepts_boundary_zero(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table_fn.return_value = mock_table

        from handler import handler

        with patch("handler.log_audit_from_context"):
            response = handler(_make_event("PUT", {"value": 0.0}), {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["confidence_threshold"] == "0.00"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_put_accepts_boundary_one(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table_fn.return_value = mock_table

        from handler import handler

        with patch("handler.log_audit_from_context"):
            response = handler(_make_event("PUT", {"value": 1.0}), {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["confidence_threshold"] == "1.00"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_put_accepts_string_number(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table_fn.return_value = mock_table

        from handler import handler

        with patch("handler.log_audit_from_context"):
            response = handler(_make_event("PUT", {"value": "0.90"}), {})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["confidence_threshold"] == "0.90"


class TestPutValidation:
    """Tests for PUT validation errors."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_put_rejects_missing_body(self, mock_auth):
        from handler import handler

        event = {
            "httpMethod": "PUT",
            "headers": {"Authorization": "Bearer fake-token"},
        }
        response = handler(event, {})

        assert response["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_put_rejects_missing_value(self, mock_auth):
        from handler import handler

        response = handler(_make_event("PUT", {"other": "field"}), {})

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "value" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_put_rejects_non_numeric_value(self, mock_auth):
        from handler import handler

        response = handler(_make_event("PUT", {"value": "abc"}), {})

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "number" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_put_rejects_value_below_zero(self, mock_auth):
        from handler import handler

        response = handler(_make_event("PUT", {"value": -0.1}), {})

        assert response["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_put_rejects_value_above_one(self, mock_auth):
        from handler import handler

        response = handler(_make_event("PUT", {"value": 1.1}), {})

        assert response["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_config_table")
    def test_put_handles_dynamodb_write_error(self, mock_table_fn, mock_auth):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = Exception("DynamoDB write error")
        mock_table_fn.return_value = mock_table

        from handler import handler

        response = handler(_make_event("PUT", {"value": 0.75}), {})

        assert response["statusCode"] == 500


class TestAccessControl:
    """Tests for admin-only access enforcement."""

    @patch(AUTH_PATCH, return_value={
        "user_id": "reporter-001",
        "email": "reporter@test.com",
        "name": "Reporter",
        "role": "reporter",
        "authorized_giveaway_years": ["2025"],
        "status": "active",
    })
    def test_reporter_denied(self, mock_auth):
        from handler import handler

        response = handler(_make_event("GET"), {})

        assert response["statusCode"] == 403

    @patch(AUTH_PATCH, return_value={
        "user_id": "submitter-001",
        "email": "submitter@test.com",
        "name": "Submitter",
        "role": "submitter",
        "authorized_giveaway_years": [],
        "status": "active",
    })
    def test_submitter_denied(self, mock_auth):
        from handler import handler

        response = handler(_make_event("GET"), {})

        assert response["statusCode"] == 403


class TestMethodNotAllowed:
    """Tests for unsupported HTTP methods."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_post_returns_405(self, mock_auth):
        from handler import handler

        response = handler(_make_event("POST"), {})

        assert response["statusCode"] == 405

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_delete_returns_405(self, mock_auth):
        from handler import handler

        response = handler(_make_event("DELETE"), {})

        assert response["statusCode"] == 405
