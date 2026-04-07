"""Unit tests for manage_reports Lambda handler.

Tests cover:
- Create saved report (Req 11.8)
- List saved reports for current user (Req 11.9)
- Load saved report — restore columns, filters, groupings, sort order (Req 11.10)
- Update saved report
- Delete saved report (Req 11.9)
- Validation and error handling
- Role-based access control (admin and reporter allowed)

Requirements: 11.8, 11.9, 11.10
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _make_event(method="GET", body=None, path_params=None):
    """Build an API Gateway proxy event."""
    event = {
        "httpMethod": method,
        "headers": {"Authorization": "Bearer fake-token"},
        "pathParameters": path_params,
    }
    if body is not None:
        event["body"] = json.dumps(body)
    else:
        event["body"] = None
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


def _reporter_context():
    return {
        "user_id": "reporter-001",
        "email": "reporter@test.com",
        "name": "Reporter User",
        "role": "reporter",
        "authorized_giveaway_years": ["2025"],
        "status": "active",
    }


SAMPLE_REPORT = {
    "name": "Height Distribution 2025",
    "columns": ["child_first_name", "child_last_name", "height_inches", "age"],
    "filters": [{"field": "giveaway_year", "operator": "equals", "value": "2025"}],
    "group_by": "height_inches",
    "sort_by": "height_inches",
    "sort_order": "asc",
}


def _stored_report(user_id="admin-001", report_id="rpt-abc123"):
    """Build a stored report item as it would appear in DynamoDB."""
    return {
        "user_id": user_id,
        "report_id": report_id,
        "name": "Height Distribution 2025",
        "columns": ["child_first_name", "child_last_name", "height_inches", "age"],
        "filters": [{"field": "giveaway_year", "operator": "equals", "value": "2025"}],
        "group_by": "height_inches",
        "sort_by": "height_inches",
        "sort_order": "asc",
        "created_at": "2025-11-10T00:00:00Z",
        "updated_at": "2025-11-15T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Create saved report (Req 11.8)
# ---------------------------------------------------------------------------
AUDIT_PATCH = "handler.log_audit_from_context"


@patch(AUDIT_PATCH)
@patch("handler._get_table")
@patch(AUTH_PATCH)
class TestCreateReport:
    def test_create_report_success(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("POST", body=SAMPLE_REPORT)
        result = handler(event, {})

        assert result["statusCode"] == 201
        body = json.loads(result["body"])
        assert body["name"] == "Height Distribution 2025"
        assert body["columns"] == SAMPLE_REPORT["columns"]
        assert body["filters"] == SAMPLE_REPORT["filters"]
        assert body["group_by"] == "height_inches"
        assert body["sort_by"] == "height_inches"
        assert body["sort_order"] == "asc"
        assert body["user_id"] == "admin-001"
        assert body["report_id"].startswith("rpt-")
        assert "created_at" in body
        assert "updated_at" in body
        mock_table.put_item.assert_called_once()
        mock_audit.assert_called_once()

    def test_create_report_missing_name(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("POST", body={"columns": []})
        result = handler(event, {})

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "name" in body["error"].lower()

    def test_create_report_empty_name(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("POST", body={"name": "   ", "columns": []})
        result = handler(event, {})

        assert result["statusCode"] == 400

    def test_create_report_invalid_columns(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("POST", body={"name": "Test", "columns": "not-a-list"})
        result = handler(event, {})

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "columns" in body["error"].lower()

    def test_create_report_reporter_allowed(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _reporter_context()
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("POST", body=SAMPLE_REPORT)
        result = handler(event, {})

        assert result["statusCode"] == 201
        body = json.loads(result["body"])
        assert body["user_id"] == "reporter-001"


# ---------------------------------------------------------------------------
# List saved reports (Req 11.9)
# ---------------------------------------------------------------------------
@patch("handler._get_table")
@patch(AUTH_PATCH)
class TestListReports:
    def test_list_reports_returns_user_reports(self, mock_auth, mock_get_table):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                _stored_report("admin-001", "rpt-001"),
                _stored_report("admin-001", "rpt-002"),
            ]
        }
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("GET")
        result = handler(event, {})

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["reports"]) == 2

    def test_list_reports_empty(self, mock_auth, mock_get_table):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("GET")
        result = handler(event, {})

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["reports"] == []


# ---------------------------------------------------------------------------
# Load saved report (Req 11.10)
# ---------------------------------------------------------------------------
@patch("handler._get_table")
@patch(AUTH_PATCH)
class TestLoadReport:
    def test_load_report_restores_config(self, mock_auth, mock_get_table):
        """Req 11.10: Restore columns, filters, groupings, sort order."""
        mock_auth.return_value = _admin_context()
        stored = _stored_report("admin-001", "rpt-abc123")
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": stored}
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("GET", path_params={"id": "rpt-abc123"})
        result = handler(event, {})

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["name"] == "Height Distribution 2025"
        assert body["columns"] == stored["columns"]
        assert body["filters"] == stored["filters"]
        assert body["group_by"] == "height_inches"
        assert body["sort_by"] == "height_inches"
        assert body["sort_order"] == "asc"

    def test_load_report_not_found(self, mock_auth, mock_get_table):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("GET", path_params={"id": "rpt-nonexistent"})
        result = handler(event, {})

        assert result["statusCode"] == 404


# ---------------------------------------------------------------------------
# Update saved report
# ---------------------------------------------------------------------------
@patch(AUDIT_PATCH)
@patch("handler._get_table")
@patch(AUTH_PATCH)
class TestUpdateReport:
    def test_update_report_success(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()
        stored = _stored_report("admin-001", "rpt-abc123")
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": stored}
        mock_get_table.return_value = mock_table

        from handler import handler

        updated_body = {
            "name": "Updated Report Name",
            "columns": ["status"],
            "filters": [],
            "sort_by": "status",
            "sort_order": "desc",
        }
        event = _make_event("PUT", body=updated_body, path_params={"id": "rpt-abc123"})
        result = handler(event, {})

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["name"] == "Updated Report Name"
        assert body["columns"] == ["status"]
        assert body["sort_order"] == "desc"
        # Preserves original created_at
        assert body["created_at"] == stored["created_at"]
        mock_table.put_item.assert_called_once()
        mock_audit.assert_called_once()

    def test_update_report_not_found(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event(
            "PUT",
            body={"name": "Test", "columns": []},
            path_params={"id": "rpt-nonexistent"},
        )
        result = handler(event, {})

        assert result["statusCode"] == 404

    def test_update_report_missing_id(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("PUT", body={"name": "Test", "columns": []})
        result = handler(event, {})

        assert result["statusCode"] == 400


# ---------------------------------------------------------------------------
# Delete saved report (Req 11.9)
# ---------------------------------------------------------------------------
@patch(AUDIT_PATCH)
@patch("handler._get_table")
@patch(AUTH_PATCH)
class TestDeleteReport:
    def test_delete_report_success(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()
        stored = _stored_report("admin-001", "rpt-abc123")
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": stored}
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("DELETE", path_params={"id": "rpt-abc123"})
        result = handler(event, {})

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["report_id"] == "rpt-abc123"
        mock_table.delete_item.assert_called_once_with(
            Key={"user_id": "admin-001", "report_id": "rpt-abc123"}
        )
        mock_audit.assert_called_once()

    def test_delete_report_not_found(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("DELETE", path_params={"id": "rpt-nonexistent"})
        result = handler(event, {})

        assert result["statusCode"] == 404

    def test_delete_report_missing_id(self, mock_auth, mock_get_table, mock_audit):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("DELETE")
        result = handler(event, {})

        assert result["statusCode"] == 400


# ---------------------------------------------------------------------------
# Error handling and edge cases
# ---------------------------------------------------------------------------
@patch(AUTH_PATCH)
class TestErrorHandling:
    def test_unsupported_method(self, mock_auth):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("PATCH")
        result = handler(event, {})

        assert result["statusCode"] == 405

    def test_post_missing_body(self, mock_auth):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("POST")
        result = handler(event, {})

        assert result["statusCode"] == 400

    def test_post_invalid_json(self, mock_auth):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = {
            "httpMethod": "POST",
            "body": "not-json",
            "headers": {"Authorization": "Bearer fake"},
            "pathParameters": None,
        }
        result = handler(event, {})

        assert result["statusCode"] == 400

    def test_submitter_denied(self, mock_auth):
        mock_auth.return_value = {
            "user_id": "sub-001",
            "email": "sub@test.com",
            "name": "Submitter",
            "role": "submitter",
            "authorized_giveaway_years": [],
            "status": "active",
        }

        from handler import handler

        event = _make_event("GET")
        result = handler(event, {})

        assert result["statusCode"] == 403

    @patch("handler._get_table")
    def test_dynamodb_error_on_create(self, mock_get_table, mock_auth):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_table.put_item.side_effect = Exception("DynamoDB error")
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("POST", body=SAMPLE_REPORT)
        result = handler(event, {})

        assert result["statusCode"] == 500

    @patch("handler._get_table")
    def test_dynamodb_error_on_list(self, mock_get_table, mock_auth):
        mock_auth.return_value = _admin_context()
        mock_table = MagicMock()
        mock_table.query.side_effect = Exception("DynamoDB error")
        mock_get_table.return_value = mock_table

        from handler import handler

        event = _make_event("GET")
        result = handler(event, {})

        assert result["statusCode"] == 500

    def test_invalid_filters_type(self, mock_auth):
        mock_auth.return_value = _admin_context()

        from handler import handler

        event = _make_event("POST", body={"name": "Test", "filters": "not-a-list"})
        result = handler(event, {})

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "filters" in body["error"].lower()
