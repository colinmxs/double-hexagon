"""Unit tests for export_data Lambda handler.

Tests cover:
- Bike build list CSV columns and content (Requirement 6.1)
- Family contact list CSV columns and content (Requirement 6.2)
- Status filtering (Requirement 6.3)
- Header row present (Requirement 6.5)
- Drawing keywords formatted as semicolon-separated (Requirement 10.5)
- Audit log recording for export (Requirement 15.5)
- Reporter year scoping (Requirement 14.6)
- Error handling

Requirements: 6.1, 6.2, 6.3, 6.5, 10.5, 15.5
"""

import csv
import io
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
    giveaway_year="2025",
    status="manually_approved",
    parent_first="Maria",
    parent_last="Garcia",
    phone="208-555-0101",
    email="maria@example.com",
    address="123 Main St",
    city="Boise",
    zip_code="83702",
    primary_language="Spanish",
    preferred_contact="WhatsApp",
    transportation=True,
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
                "dream_bike_description": "A blue mountain bike with streamers",
                "drawing_keywords": ["blue", "mountain bike", "streamers"],
                "bike_number": "B-2025-042",
            }
        ]
    return {
        "giveaway_year": giveaway_year,
        "application_id": app_id,
        "status": status,
        "referring_agency": {"agency_name": agency_name},
        "parent_guardian": {
            "first_name": parent_first,
            "last_name": parent_last,
            "phone": phone,
            "email": email,
            "address": address,
            "city": city,
            "zip_code": zip_code,
            "primary_language": primary_language,
            "preferred_contact_method": preferred_contact,
            "transportation_access": transportation,
        },
        "children": children,
    }


def _parse_csv(csv_string):
    """Parse a CSV string into a list of rows (each row is a list of strings)."""
    reader = csv.reader(io.StringIO(csv_string))
    return list(reader)


class TestBikeBuildListCSV:
    """Tests for Bike Build List CSV generation (Requirement 6.1)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_bike_build_csv_headers(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert result["statusCode"] == 200
        assert rows[0] == [
            "Child First Name",
            "Child Last Name",
            "Height (inches)",
            "Age",
            "Gender",
            "Bike Color 1",
            "Bike Color 2",
            "Knows How to Ride",
            "Dream Bike Description",
            "Drawing Keywords",
            "Bike Number",
        ]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_bike_build_csv_content(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert len(rows) == 2  # header + 1 child
        data_row = rows[1]
        assert data_row[0] == "Carlos"       # Child First Name
        assert data_row[1] == "Garcia"        # Child Last Name
        assert data_row[2] == "48"            # Height
        assert data_row[3] == "8"             # Age
        assert data_row[4] == "Male"          # Gender
        assert data_row[5] == "Blue"          # Bike Color 1
        assert data_row[6] == "Black"         # Bike Color 2
        assert data_row[7] == "Yes"           # Knows How to Ride
        assert data_row[8] == "A blue mountain bike with streamers"
        assert data_row[10] == "B-2025-042"   # Bike Number

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_bike_build_multiple_children(self, mock_table, mock_audit, mock_auth):
        from handler import handler

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
                "dream_bike_description": "",
                "drawing_keywords": [],
                "bike_number": "",
            },
            {
                "child_id": "child-002",
                "first_name": "Sofia",
                "last_name": "Garcia",
                "height_inches": Decimal("42"),
                "age": Decimal("6"),
                "gender": "Female",
                "bike_color_1": "Pink",
                "bike_color_2": "Purple",
                "knows_how_to_ride": False,
                "dream_bike_description": "A pink bike",
                "drawing_keywords": ["pink", "cruiser"],
                "bike_number": "B-2025-043",
            },
        ]
        app = _make_application(children=children)
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [app]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert len(rows) == 3  # header + 2 children
        assert rows[1][0] == "Carlos"
        assert rows[2][0] == "Sofia"
        assert rows[2][7] == "No"  # knows_how_to_ride = False


class TestDrawingKeywordsFormat:
    """Tests for Drawing Keywords semicolon-separated format (Requirement 10.5)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_drawing_keywords_semicolon_separated(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        # Drawing Keywords column (index 9)
        assert rows[1][9] == "blue;mountain bike;streamers"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_empty_drawing_keywords(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        children = [{
            "child_id": "child-001",
            "first_name": "Test",
            "last_name": "Child",
            "height_inches": Decimal("40"),
            "age": Decimal("5"),
            "gender": "Male",
            "bike_color_1": "Red",
            "bike_color_2": "White",
            "knows_how_to_ride": False,
            "dream_bike_description": "",
            "drawing_keywords": [],
            "bike_number": "",
        }]
        app = _make_application(children=children)
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [app]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert rows[1][9] == ""


class TestFamilyContactListCSV:
    """Tests for Family Contact List CSV generation (Requirement 6.2)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_family_contact_csv_headers(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "family_contact_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert result["statusCode"] == 200
        assert rows[0] == [
            "Parent/Guardian First Name",
            "Last Name",
            "Phone",
            "Email",
            "Address",
            "City",
            "Zip Code",
            "Primary Language",
            "Preferred Contact Method",
            "Transportation Access",
            "Referring Agency Name",
        ]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_family_contact_csv_multiple_applications(self, mock_table, mock_audit, mock_auth):
        """Verify one row per application in family contact list (Requirement 6.2)."""
        from handler import handler

        app1 = _make_application(app_id="APP001", parent_first="Maria", parent_last="Garcia")
        app2 = _make_application(
            app_id="APP002",
            parent_first="John",
            parent_last="Smith",
            phone="208-555-0202",
            email="john@example.com",
            address="456 Oak Ave",
            city="Meridian",
            zip_code="83646",
            primary_language="English",
            preferred_contact="Phone Call",
            transportation=False,
            agency_name="Other Agency",
        )
        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [app1, app2]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "family_contact_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert len(rows) == 3  # header + 2 applications
        assert rows[1][0] == "Maria"
        assert rows[2][0] == "John"
        assert rows[2][9] == "No"  # transportation_access = False
        assert rows[2][10] == "Other Agency"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_family_contact_csv_content(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "family_contact_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert len(rows) == 2  # header + 1 application
        data_row = rows[1]
        assert data_row[0] == "Maria"
        assert data_row[1] == "Garcia"
        assert data_row[2] == "208-555-0101"
        assert data_row[3] == "maria@example.com"
        assert data_row[4] == "123 Main St"
        assert data_row[5] == "Boise"
        assert data_row[6] == "83702"
        assert data_row[7] == "Spanish"
        assert data_row[8] == "WhatsApp"
        assert data_row[9] == "Yes"
        assert data_row[10] == "Partner Org"


class TestStatusFiltering:
    """Tests for status filtering (Requirement 6.3)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_status_filter_uses_gsi(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
            "status_filter": "manually_approved",
        })
        result = handler(event, None)

        assert result["statusCode"] == 200
        call_kwargs = mock_tbl.query.call_args[1]
        assert call_kwargs["IndexName"] == "status-index"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_no_status_filter_queries_all(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)

        assert result["statusCode"] == 200
        call_kwargs = mock_tbl.query.call_args[1]
        assert "IndexName" not in call_kwargs

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_status_filter_only_returns_matching(self, mock_table, mock_audit, mock_auth):
        """Verify that only applications matching the status filter appear in the export."""
        from handler import handler

        approved_app = _make_application(app_id="APP001", status="manually_approved")
        mock_tbl = MagicMock()
        # GSI query returns only the matching application
        mock_tbl.query.return_value = {"Items": [approved_app]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "family_contact_list",
            "giveaway_year": "2025",
            "status_filter": "manually_approved",
        })
        result = handler(event, None)
        body = json.loads(result["body"])
        rows = _parse_csv(body["csv_content"])

        assert result["statusCode"] == 200
        assert body["record_count"] == 1
        assert len(rows) == 2  # header + 1 matching application


class TestAuditLogging:
    """Tests for audit log recording on export (Requirement 15.5)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_audit_log_recorded_for_bike_build(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
            "status_filter": "manually_approved",
        })
        handler(event, None)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["action_type"] == "export"
        assert call_kwargs["resource_type"] == "application"
        assert "bike_build_list" in call_kwargs["resource_id"]
        details = call_kwargs["details"]
        assert details["export_type"] == "bike_build_list"
        assert details["giveaway_year"] == "2025"
        assert details["status_filter"] == "manually_approved"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_audit_log_no_status_filter(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "family_contact_list",
            "giveaway_year": "2025",
        })
        handler(event, None)

        call_kwargs = mock_audit.call_args[1]
        details = call_kwargs["details"]
        assert details["export_type"] == "family_contact_list"
        assert "status_filter" not in details


class TestReporterYearScoping:
    """Tests for reporter giveaway year scoping (Requirement 14.6)."""

    @patch(AUTH_PATCH, return_value=_reporter_context(years=["2025"]))
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_reporter_allowed_for_authorized_year(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": []}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        assert result["statusCode"] == 200

    @patch(AUTH_PATCH, return_value=_reporter_context(years=["2025"]))
    def test_reporter_denied_for_unauthorized_year(self, mock_auth):
        from handler import handler

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2024",
        })
        result = handler(event, None)
        assert result["statusCode"] == 403
        body = json.loads(result["body"])
        assert "not authorized" in body["error"].lower()


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_missing_body_returns_400(self, mock_auth):
        from handler import handler

        event = {"body": None, "headers": {"Authorization": "Bearer fake"}}
        result = handler(event, None)
        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_invalid_export_type_returns_400(self, mock_auth):
        from handler import handler

        event = _make_event({"export_type": "invalid_type", "giveaway_year": "2025"})
        result = handler(event, None)
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "export_type" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_missing_export_type_returns_400(self, mock_auth):
        from handler import handler

        event = _make_event({"giveaway_year": "2025"})
        result = handler(event, None)
        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler._get_active_giveaway_year", return_value=None)
    def test_no_active_year_returns_500(self, mock_year, mock_auth):
        from handler import handler

        event = _make_event({"export_type": "bike_build_list"})
        result = handler(event, None)
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "active giveaway year" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_dynamodb_error_returns_500(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.side_effect = Exception("DynamoDB error")
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        assert result["statusCode"] == 500

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.log_audit_from_context")
    @patch("handler.get_dynamodb_table")
    def test_response_includes_metadata(self, mock_table, mock_audit, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.query.return_value = {"Items": [_make_application()]}
        mock_table.return_value = mock_tbl

        event = _make_event({
            "export_type": "bike_build_list",
            "giveaway_year": "2025",
        })
        result = handler(event, None)
        body = json.loads(result["body"])

        assert body["export_type"] == "bike_build_list"
        assert body["giveaway_year"] == "2025"
        assert body["record_count"] == 1
        assert body["content_type"] == "text/csv"
