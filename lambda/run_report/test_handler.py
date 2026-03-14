"""Unit tests for run_report Lambda handler.

Tests cover:
- Filter operators: equals, contains, greater_than, less_than, between, in_list (Req 11.3)
- Grouping and aggregate counts (Req 11.4)
- Summary statistics (Req 11.5)
- Sorting ascending/descending (Req 11.7)
- Real-time filtering (Req 11.13)
- Pagination (Req 11.14)
- Reporter giveaway year scoping (Req 14.6)
- Column selection (Req 11.2)
- Error handling

Requirements: 11.2, 11.3, 11.4, 11.5, 11.7, 11.13, 11.14, 14.6
"""

import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _make_event(body=None):
    """Build an API Gateway proxy event with a JSON body."""
    return {
        "body": json.dumps(body or {}),
        "headers": {"Authorization": "Bearer fake-token"},
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


def _make_application(
    app_id="APP001",
    status="manually_approved",
    source_type="digital",
    parent_first="Maria",
    parent_last="Garcia",
    agency_name="Partner Org",
    children=None,
):
    """Build a sample application record."""
    if children is None:
        children = [
            {
                "child_id": "child-001",
                "first_name": "Carlos",
                "last_name": "Garcia",
                "height_inches": Decimal("48"),
                "age": Decimal("8"),
                "gender": "Male",
                "bike_color_1": "Blue",
                "bike_color_2": "Black",
                "knows_how_to_ride": True,
            }
        ]
    return {
        "giveaway_year": "2025",
        "application_id": app_id,
        "status": status,
        "source_type": source_type,
        "referring_agency": {"agency_name": agency_name},
        "parent_guardian": {
            "first_name": parent_first,
            "last_name": parent_last,
            "phone": "208-555-0101",
            "email": "test@example.com",
        },
        "children": children,
    }


SAMPLE_APPS = [
    _make_application("APP001", "manually_approved", "digital", "Maria", "Garcia", "Agency A"),
    _make_application("APP002", "needs_review", "upload", "John", "Smith", "Agency B"),
    _make_application(
        "APP003", "auto_approved", "digital", "Ana", "Lopez", "Agency A",
        children=[
            {"child_id": "c1", "first_name": "Sofia", "last_name": "Lopez",
             "height_inches": Decimal("42"), "age": Decimal("6"), "gender": "Female",
             "bike_color_1": "Pink", "bike_color_2": "White", "knows_how_to_ride": False},
            {"child_id": "c2", "first_name": "Diego", "last_name": "Lopez",
             "height_inches": Decimal("52"), "age": Decimal("10"), "gender": "Male",
             "bike_color_1": "Red", "bike_color_2": "Black", "knows_how_to_ride": True},
        ],
    ),
]


def _mock_table_with_items(items):
    """Create a mock DynamoDB table that returns the given items."""
    mock_table = MagicMock()
    mock_table.query.return_value = {"Items": items}
    return mock_table


class TestSummaryStatistics:
    """Tests for summary statistics computation (Requirement 11.5)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_summary_includes_totals(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": ["status"]})
        result = handler(event, None)
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        summary = body["summary"]
        assert summary["total_applications"] == 3
        # APP001 has 1 child, APP002 has 1 child, APP003 has 2 children
        assert summary["total_children"] == 4

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_summary_by_status(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": ["status"]})
        result = handler(event, None)
        body = json.loads(result["body"])

        by_status = body["summary"]["applications_by_status"]
        assert by_status["manually_approved"] == 1
        assert by_status["needs_review"] == 1
        assert by_status["auto_approved"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_summary_by_source_type(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": ["source_type"]})
        result = handler(event, None)
        body = json.loads(result["body"])

        by_source = body["summary"]["applications_by_source_type"]
        assert by_source["digital"] == 2
        assert by_source["upload"] == 1


class TestFilterOperators:
    """Tests for filter operators (Requirement 11.3)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_equals_filter(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status", "parent_guardian.last_name"],
            "filters": [{"field": "status", "operator": "equals", "value": "needs_review"}],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["summary"]["total_applications"] == 1
        assert len(body["rows"]) == 1
        assert body["rows"][0]["parent_guardian.last_name"] == "Smith"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_contains_filter(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["parent_guardian.last_name"],
            "filters": [{"field": "parent_guardian.last_name", "operator": "contains", "value": "arc"}],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["summary"]["total_applications"] == 1
        assert body["rows"][0]["parent_guardian.last_name"] == "Garcia"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_greater_than_filter(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["children[0].height_inches"],
            "filters": [{"field": "children[0].height_inches", "operator": "greater_than", "value": 45}],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        # APP001 child height=48, APP003 child[0] height=42 (excluded), APP002 child height=48
        assert body["summary"]["total_applications"] == 2

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_less_than_filter(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["children[0].age"],
            "filters": [{"field": "children[0].age", "operator": "less_than", "value": 7}],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        # Only APP003 child[0] age=6 is less than 7
        assert body["summary"]["total_applications"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_between_filter(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["children[0].age"],
            "filters": [{"field": "children[0].age", "operator": "between", "value": [6, 8]}],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        # APP001 age=8 (included), APP002 age=8 (included), APP003 child[0] age=6 (included)
        assert body["summary"]["total_applications"] == 3

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_in_list_filter(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
            "filters": [{"field": "status", "operator": "in_list", "value": ["manually_approved", "auto_approved"]}],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["summary"]["total_applications"] == 2

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_multiple_filters_and_logic(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status", "source_type"],
            "filters": [
                {"field": "source_type", "operator": "equals", "value": "digital"},
                {"field": "status", "operator": "equals", "value": "auto_approved"},
            ],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        # Only APP003 is digital + auto_approved
        assert body["summary"]["total_applications"] == 1


class TestGrouping:
    """Tests for group-by with aggregate counts (Requirement 11.4)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_group_by_status(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
            "group_by": "status",
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert "groups" in body
        groups = body["groups"]
        assert groups["manually_approved"]["count"] == 1
        assert groups["needs_review"]["count"] == 1
        assert groups["auto_approved"]["count"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_group_by_source_type(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["source_type"],
            "group_by": "source_type",
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        groups = body["groups"]
        assert groups["digital"]["count"] == 2
        assert groups["upload"]["count"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_no_group_by_omits_groups_key(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert "groups" not in body


class TestSorting:
    """Tests for sorting (Requirement 11.7)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_sort_ascending(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["parent_guardian.last_name"],
            "sort_by": "parent_guardian.last_name",
            "sort_order": "asc",
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        names = [r["parent_guardian.last_name"] for r in body["rows"]]
        assert names == ["Garcia", "Lopez", "Smith"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_sort_descending(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["parent_guardian.last_name"],
            "sort_by": "parent_guardian.last_name",
            "sort_order": "desc",
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        names = [r["parent_guardian.last_name"] for r in body["rows"]]
        assert names == ["Smith", "Lopez", "Garcia"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_sort_numeric_field(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["children[0].height_inches"],
            "sort_by": "children[0].height_inches",
            "sort_order": "asc",
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        heights = [r["children[0].height_inches"] for r in body["rows"]]
        assert heights == [42, 48, 48]


class TestPagination:
    """Tests for pagination (Requirement 11.14)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_default_page_size(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": ["status"]})
        result = handler(event, None)
        body = json.loads(result["body"])

        pagination = body["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 50
        assert pagination["total_count"] == 3
        assert pagination["total_pages"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_custom_page_size(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
            "page_size": 2,
            "page": 1,
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert len(body["rows"]) == 2
        assert body["pagination"]["total_pages"] == 2
        assert body["pagination"]["total_count"] == 3

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_second_page(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
            "page_size": 2,
            "page": 2,
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert len(body["rows"]) == 1
        assert body["pagination"]["page"] == 2

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_page_size_clamped_to_max(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
            "page_size": 999,
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["pagination"]["page_size"] == 200


class TestReporterYearScoping:
    """Tests for reporter giveaway year scoping (Requirement 14.6)."""

    @patch(AUTH_PATCH, return_value=_reporter_context(["2025"]))
    @patch("handler.get_dynamodb_table")
    def test_reporter_allowed_for_authorized_year(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": ["status"]})
        result = handler(event, None)

        assert result["statusCode"] == 200

    @patch(AUTH_PATCH, return_value=_reporter_context(["2024"]))
    def test_reporter_denied_for_unauthorized_year(self, mock_auth):
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": ["status"]})
        result = handler(event, None)

        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert "not authorized" in body["error"].lower()


class TestColumnSelection:
    """Tests for column selection (Requirement 11.2)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_selected_columns_returned(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["parent_guardian.first_name", "status"],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        for row in body["rows"]:
            assert "parent_guardian.first_name" in row
            assert "status" in row
            # Should not have other fields
            assert len(row) == 2

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_nested_field_resolution(self, mock_get_table, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["referring_agency.agency_name", "children[0].first_name"],
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["rows"][0]["referring_agency.agency_name"] == "Agency A"
        assert body["rows"][0]["children[0].first_name"] == "Carlos"


class TestErrorHandling:
    """Tests for error handling."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_missing_body_returns_400(self, mock_auth):
        from handler import handler

        event = {"body": None, "headers": {"Authorization": "Bearer fake"}}
        result = handler(event, None)
        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_invalid_json_returns_400(self, mock_auth):
        from handler import handler

        event = {"body": "not-json", "headers": {"Authorization": "Bearer fake"}}
        result = handler(event, None)
        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_invalid_filter_operator_returns_400(self, mock_auth):
        from handler import handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
            "filters": [{"field": "status", "operator": "invalid_op", "value": "x"}],
        })
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "invalid filter operator" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_columns_not_list_returns_400(self, mock_auth):
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": "not-a-list"})
        result = handler(event, None)
        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_no_active_year_returns_500(self, mock_get_table, mock_auth):
        mock_config_table = MagicMock()
        mock_config_table.get_item.return_value = {}
        mock_get_table.return_value = mock_config_table
        from handler import handler

        event = _make_event({"columns": ["status"]})
        result = handler(event, None)
        assert result["statusCode"] == 500

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_dynamodb_error_returns_500(self, mock_get_table, mock_auth):
        mock_table = MagicMock()
        mock_table.query.side_effect = Exception("DynamoDB error")
        mock_get_table.return_value = mock_table
        from handler import handler

        event = _make_event({"giveaway_year": "2025", "columns": ["status"]})
        result = handler(event, None)
        assert result["statusCode"] == 500


class TestExportHandler:
    """Tests for CSV export endpoint (Requirements 11.11, 15.5)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_returns_csv_content_type(self, mock_get_table, mock_audit, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status", "parent_guardian.last_name"],
        })
        result = export_handler(event, None)

        assert result["statusCode"] == 200
        assert result["headers"]["Content-Type"] == "text/csv"
        assert "attachment" in result["headers"]["Content-Disposition"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_csv_has_header_row(self, mock_get_table, mock_audit, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status", "parent_guardian.last_name"],
        })
        result = export_handler(event, None)
        lines = result["body"].strip().split("\n")

        # First line is the header
        assert lines[0].strip() == "status,parent_guardian.last_name"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_csv_has_data_rows(self, mock_get_table, mock_audit, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status", "parent_guardian.last_name"],
        })
        result = export_handler(event, None)
        lines = result["body"].strip().split("\n")

        # Header + 3 data rows
        assert len(lines) == 4

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_applies_filters(self, mock_get_table, mock_audit, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status", "parent_guardian.last_name"],
            "filters": [{"field": "status", "operator": "equals", "value": "needs_review"}],
        })
        result = export_handler(event, None)
        lines = result["body"].strip().split("\n")

        # Header + 1 filtered row
        assert len(lines) == 2
        assert "Smith" in lines[1]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_records_audit_log(self, mock_get_table, mock_audit, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
            "filters": [{"field": "status", "operator": "equals", "value": "needs_review"}],
        })
        export_handler(event, None)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args
        assert call_kwargs[1]["action_type"] == "export"
        assert call_kwargs[1]["resource_type"] == "report"
        assert call_kwargs[1]["details"]["export_type"] == "report"
        assert call_kwargs[1]["details"]["giveaway_year"] == "2025"
        assert call_kwargs[1]["details"]["row_count"] == 1

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_export_empty_columns_returns_400(self, mock_auth):
        from handler import export_handler

        event = _make_event({"giveaway_year": "2025", "columns": []})
        result = export_handler(event, None)
        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_reporter_context(["2024"]))
    def test_export_reporter_denied_unauthorized_year(self, mock_auth):
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
        })
        result = export_handler(event, None)
        assert result["statusCode"] == 403

    @patch(AUTH_PATCH, return_value=_reporter_context(["2025"]))
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_reporter_allowed_authorized_year(self, mock_get_table, mock_audit, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
        })
        result = export_handler(event, None)
        assert result["statusCode"] == 200

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_applies_sorting(self, mock_get_table, mock_audit, mock_auth):
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["parent_guardian.last_name"],
            "sort_by": "parent_guardian.last_name",
            "sort_order": "asc",
        })
        result = export_handler(event, None)
        lines = result["body"].strip().split("\n")

        # Header + 3 sorted rows
        assert lines[1].strip() == "Garcia"
        assert lines[2].strip() == "Lopez"
        assert lines[3].strip() == "Smith"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_export_no_pagination(self, mock_get_table, mock_audit, mock_auth):
        """Export returns ALL filtered rows, not paginated."""
        mock_get_table.return_value = _mock_table_with_items(SAMPLE_APPS)
        from handler import export_handler

        event = _make_event({
            "giveaway_year": "2025",
            "columns": ["status"],
        })
        result = export_handler(event, None)
        lines = result["body"].strip().split("\n")

        # All 3 apps exported (no pagination)
        assert len(lines) == 4  # header + 3 data rows
