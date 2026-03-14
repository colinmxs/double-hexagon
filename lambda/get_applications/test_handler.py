"""Unit tests for get_applications Lambda handler.

Tests cover:
- Query by giveaway year (Requirement 17.3)
- Status filtering (Requirement 5.2)
- Search by family name and agency name (Requirement 5.3)
- Pagination with next_token (Requirement 5.1)
- Reporter year scoping enforcement (Requirement 14.6)
- Error handling

Requirements: 5.1, 5.2, 5.3, 14.6, 17.3
"""

import base64
import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))


def _make_event(query_params=None):
    """Helper to build an API Gateway proxy event with query string parameters."""
    return {
        "queryStringParameters": query_params or {},
        "headers": {"Authorization": "Bearer fake-token"},
    }


def _make_application(app_id="APP001", last_name="Smith", status="needs_review",
                       agency_name="Partner Org", source_type="upload",
                       confidence=Decimal("0.85"), giveaway_year="2025",
                       drawing_s3_key=None):
    """Build a sample application record."""
    children = [
        {
            "child_id": "child-001",
            "first_name": "Alice",
            "last_name": last_name,
            "drawing_image_s3_key": drawing_s3_key,
        }
    ]
    return {
        "giveaway_year": giveaway_year,
        "application_id": app_id,
        "submission_timestamp": "2025-11-15T10:30:00.000Z",
        "source_type": source_type,
        "status": status,
        "overall_confidence_score": confidence,
        "referring_agency": {"agency_name": agency_name},
        "parent_guardian": {"last_name": last_name, "first_name": "John"},
        "children": children,
    }


def _admin_context():
    return {
        "user_id": "admin-001",
        "email": "admin@test.com",
        "name": "Admin User",
        "role": "admin",
        "authorized_giveaway_years": [],
        "status": "active",
    }


def _reporter_context(years=None):
    return {
        "user_id": "reporter-001",
        "email": "reporter@test.com",
        "name": "Reporter User",
        "role": "reporter",
        "authorized_giveaway_years": years or ["2025"],
        "status": "active",
    }


# Patch authenticate as imported into rbac module (where require_role calls it)
AUTH_PATCH = "rbac.authenticate"


class TestQueryByGiveawayYear:
    """Tests for querying applications by giveaway year."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_defaults_to_active_year(self, mock_year, mock_table, mock_auth):
        from handler import handler

        apps = [_make_application()]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event()
        result = handler(event, None)
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["giveaway_year"] == "2025"
        assert body["count"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_explicit_year_parameter(self, mock_table, mock_auth):
        from handler import handler

        apps = [_make_application(giveaway_year="2024")]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2024"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["giveaway_year"] == "2024"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_returns_formatted_fields(self, mock_year, mock_table, mock_auth):
        from handler import handler

        apps = [_make_application(app_id="A1", last_name="Garcia", status="auto_approved")]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event()
        result = handler(event, None)
        body = json.loads(result["body"])
        app = body["applications"][0]

        assert app["application_id"] == "A1"
        assert app["family_name"] == "Garcia"
        assert app["status"] == "auto_approved"
        assert "submission_timestamp" in app
        assert "source_type" in app
        assert "overall_confidence_score" in app
        assert "drawing_thumbnail_url" in app


class TestStatusFiltering:
    """Tests for filtering applications by status."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_filter_by_status_uses_gsi(self, mock_table, mock_auth):
        from handler import handler

        apps = [_make_application(status="needs_review")]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "status": "needs_review"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["count"] == 1
        # Verify the GSI was used
        call_kwargs = mock_tbl.query.call_args[1]
        assert call_kwargs["IndexName"] == "status-index"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_no_status_queries_main_table(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)

        assert result["statusCode"] == 200
        call_kwargs = mock_tbl.query.call_args[1]
        assert "IndexName" not in call_kwargs


class TestSearchFiltering:
    """Tests for searching by family name or agency name."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_search_by_family_name(self, mock_table, mock_auth):
        from handler import handler

        apps = [
            _make_application(app_id="A1", last_name="Garcia"),
            _make_application(app_id="A2", last_name="Smith"),
        ]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "search": "Garcia"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["count"] == 1
        assert body["applications"][0]["family_name"] == "Garcia"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_search_by_agency_name(self, mock_table, mock_auth):
        from handler import handler

        apps = [
            _make_application(app_id="A1", agency_name="Boys and Girls Club"),
            _make_application(app_id="A2", agency_name="United Way"),
        ]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "search": "boys"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["count"] == 1
        assert body["applications"][0]["application_id"] == "A1"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_search_case_insensitive(self, mock_table, mock_auth):
        from handler import handler

        apps = [_make_application(app_id="A1", last_name="McDonald")]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "search": "mcdonald"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["count"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_search_no_match_returns_empty(self, mock_table, mock_auth):
        from handler import handler

        apps = [_make_application(app_id="A1", last_name="Smith")]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "search": "zzzzz"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["count"] == 0
        assert body["applications"] == []

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_combined_status_filter_and_search(self, mock_table, mock_auth):
        from handler import handler

        apps = [
            _make_application(app_id="A1", last_name="Garcia", status="needs_review"),
            _make_application(app_id="A2", last_name="Smith", status="needs_review"),
        ]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "status": "needs_review", "search": "Garcia"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        assert body["count"] == 1
        assert body["applications"][0]["family_name"] == "Garcia"
        # Verify status GSI was used
        call_kwargs = mock_tbl.query.call_args[1]
        assert call_kwargs["IndexName"] == "status-index"


class TestPagination:
    """Tests for pagination with next_token."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_returns_next_token_when_more_results(self, mock_table, mock_auth):
        from handler import handler

        last_key = {"giveaway_year": "2025", "application_id": "APP050"}
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {
            "Items": [_make_application()],
            "LastEvaluatedKey": last_key,
        }
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert "next_token" in body
        # Verify the token decodes back to the original key
        decoded = json.loads(base64.b64decode(body["next_token"]))
        assert decoded["giveaway_year"] == "2025"
        assert decoded["application_id"] == "APP050"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_no_next_token_when_no_more_results(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert "next_token" not in body

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_uses_next_token_as_exclusive_start_key(self, mock_table, mock_auth):
        from handler import handler

        start_key = {"giveaway_year": "2025", "application_id": "APP050"}
        token = base64.b64encode(json.dumps(start_key).encode()).decode()

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "next_token": token})
        result = handler(event, None)

        assert result["statusCode"] == 200
        call_kwargs = mock_tbl.query.call_args[1]
        assert call_kwargs["ExclusiveStartKey"] == start_key

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_invalid_next_token_returns_400(self, mock_auth):
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "next_token": "not-valid-base64!!!"})
        result = handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "pagination" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_custom_page_size(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "page_size": "10"})
        result = handler(event, None)

        assert result["statusCode"] == 200
        call_kwargs = mock_tbl.query.call_args[1]
        assert call_kwargs["Limit"] == 10

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_page_size_capped_at_max(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025", "page_size": "999"})
        result = handler(event, None)

        assert result["statusCode"] == 200
        call_kwargs = mock_tbl.query.call_args[1]
        assert call_kwargs["Limit"] == 200


class TestReporterYearScoping:
    """Tests for reporter giveaway year scoping enforcement."""

    @patch(AUTH_PATCH, return_value=_reporter_context(years=["2025"]))
    @patch("handler.get_dynamodb_table")
    def test_reporter_allowed_for_authorized_year(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)

        assert result["statusCode"] == 200

    @patch(AUTH_PATCH, return_value=_reporter_context(years=["2025"]))
    def test_reporter_denied_for_unauthorized_year(self, mock_auth):
        from handler import handler

        event = _make_event({"giveaway_year": "2024"})
        result = handler(event, None)

        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert "not authorized" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_reporter_context(years=["2024", "2025"]))
    @patch("handler.get_dynamodb_table")
    def test_reporter_with_multiple_authorized_years(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2024"})
        result = handler(event, None)

        assert result["statusCode"] == 200


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_active_giveaway_year", return_value=None)
    def test_no_active_year_returns_500(self, mock_year, mock_auth):
        from handler import handler

        event = _make_event()
        result = handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "active giveaway year" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_active_giveaway_year", side_effect=Exception("DB error"))
    def test_config_table_error_returns_500(self, mock_year, mock_auth):
        from handler import handler

        event = _make_event()
        result = handler(event, None)

        assert result["statusCode"] == 500

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_query_failure_returns_500(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.side_effect = Exception("DynamoDB error")
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "retrieve" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_cors_headers_present(self, mock_year, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event()
        result = handler(event, None)

        assert result["headers"]["Access-Control-Allow-Origin"] == "*"


class TestDrawingThumbnail:
    """Tests for drawing thumbnail URL generation."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_presigned_get_url", return_value="https://s3.example.com/drawing.png")
    def test_drawing_thumbnail_url_generated(self, mock_presign, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        apps = [_make_application(drawing_s3_key="drawings/2025/APP001/child-001.png")]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["applications"][0]["drawing_thumbnail_url"] == "https://s3.example.com/drawing.png"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_no_drawing_returns_null(self, mock_table, mock_auth):
        from handler import handler

        apps = [_make_application(drawing_s3_key=None)]
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": apps}
        mock_table.return_value = mock_tbl

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["applications"][0]["drawing_thumbnail_url"] is None
