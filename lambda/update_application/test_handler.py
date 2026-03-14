"""Unit tests for update_application Lambda handler.

Tests cover:
- Field updates with confidence reset to 1.0 (Requirement 5.7)
- Status update to manually_approved (Requirement 5.8)
- Bike number assignment (Requirement 5.10)
- Drawing keywords editing (Requirement 5.9, 5.11)
- Version retention in S3 (Requirement 9.2)
- Audit log recording with field details (Requirement 15.3)
- Application not found returns 404
- Missing path parameters returns 400
- Error handling

Requirements: 5.7, 5.8, 5.9, 5.10, 5.11, 9.2, 15.3
"""

import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

AUTH_PATCH = "rbac.authenticate"


def _admin_context():
    return {
        "user_id": "admin-001",
        "email": "admin@test.com",
        "name": "Admin User",
        "role": "admin",
        "authorized_giveaway_years": [],
        "status": "active",
    }


def _make_event(giveaway_year="2025", application_id="APP001", body=None):
    """Build an API Gateway proxy event with path parameters and body."""
    path_params = {}
    if giveaway_year is not None:
        path_params["giveaway_year"] = giveaway_year
    if application_id is not None:
        path_params["application_id"] = application_id
    return {
        "pathParameters": path_params if path_params else None,
        "headers": {"Authorization": "Bearer fake-token"},
        "body": json.dumps(body) if body is not None else None,
    }


def _make_application(app_id="APP001", giveaway_year="2025"):
    """Build a complete application record matching the DynamoDB schema."""
    return {
        "giveaway_year": giveaway_year,
        "application_id": app_id,
        "submission_timestamp": "2025-11-15T10:30:00Z",
        "source_type": "upload",
        "status": "needs_review",
        "overall_confidence_score": Decimal("0.72"),
        "referring_agency": {
            "agency_name": "Partner Org",
            "contact_name": "Jane Doe",
            "contact_phone": "208-555-0100",
            "contact_email": "jane@partner.org",
        },
        "parent_guardian": {
            "first_name": "Maria",
            "last_name": "Garcia",
            "address": "123 Main St",
            "city": "Boise",
            "zip_code": "83702",
            "phone": "208-555-0101",
            "email": "maria@example.com",
            "primary_language": "Spanish",
            "english_speaker_in_household": False,
            "preferred_contact_method": "WhatsApp",
            "transportation_access": True,
        },
        "children": [
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
                "other_siblings_enrolled": "Sofia Garcia",
                "drawing_image_s3_key": "drawings/2025/APP001/child-001.png",
                "drawing_keywords": ["blue", "mountain bike", "streamers"],
                "dream_bike_description": "A blue mountain bike with streamers",
                "bike_number": None,
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
                "drawing_image_s3_key": "drawings/2025/APP001/child-002.png",
                "drawing_keywords": ["pink", "cruiser"],
                "dream_bike_description": "A pink bike with a basket",
                "bike_number": None,
            },
        ],
        "field_confidence": {
            "referring_agency.agency_name": Decimal("0.95"),
            "parent_guardian.first_name": Decimal("0.93"),
            "parent_guardian.phone": Decimal("0.72"),
            "children[0].first_name": Decimal("0.90"),
            "children[0].height_inches": Decimal("0.78"),
            "children[1].first_name": Decimal("0.85"),
        },
        "original_documents": [],
        "version": Decimal("2"),
        "previous_versions_s3_key": "versions/2025/APP001/v1.json",
    }


class TestFieldUpdates:
    """Tests for field updates with confidence reset to 1.0 (Requirement 5.7)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_field_update_sets_confidence_to_1(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event(body=body)
        result = handler(event, None)
        body_resp = json.loads(result["body"])

        assert result["statusCode"] == 200
        # Check the put_item was called with confidence 1.0 for the edited field
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"] if "Item" in (put_call[1] or {}) else put_call[0][0] if put_call[0] else put_call[1]["Item"]
        assert saved_app["field_confidence"]["parent_guardian.phone"] == Decimal("1.0")
        assert saved_app["parent_guardian"]["phone"] == "208-555-9999"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_multiple_field_updates(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {
            "field_updates": {
                "parent_guardian.phone": "208-555-9999",
                "referring_agency.agency_name": "New Agency",
            }
        }
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        assert saved_app["field_confidence"]["parent_guardian.phone"] == Decimal("1.0")
        assert saved_app["field_confidence"]["referring_agency.agency_name"] == Decimal("1.0")
        assert saved_app["parent_guardian"]["phone"] == "208-555-9999"
        assert saved_app["referring_agency"]["agency_name"] == "New Agency"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_version_incremented(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        # Original version was 2, should now be 3
        assert saved_app["version"] == 3
        del os.environ["DOCUMENTS_BUCKET"]


class TestStatusUpdate:
    """Tests for status update to manually_approved (Requirement 5.8)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_status_update_to_manually_approved(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"status": "manually_approved"}
        event = _make_event(body=body)
        result = handler(event, None)
        body_resp = json.loads(result["body"])

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        assert saved_app["status"] == "manually_approved"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_status_update_audit_log(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"status": "manually_approved"}
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        mock_audit.assert_called_once()
        audit_call = mock_audit.call_args
        details = audit_call[1]["details"]
        changes = details["changes"]
        status_change = [c for c in changes if c["field_name"] == "status"][0]
        assert status_change["previous_value"] == "needs_review"
        assert status_change["new_value"] == "manually_approved"
        del os.environ["DOCUMENTS_BUCKET"]


class TestBikeNumberAssignment:
    """Tests for bike number assignment (Requirement 5.10)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_assign_bike_number(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {
            "children_updates": [
                {"child_id": "child-001", "bike_number": "B-2025-042"}
            ]
        }
        event = _make_event(body=body)
        result = handler(event, None)
        body_resp = json.loads(result["body"])

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        child = saved_app["children"][0]
        assert child["bike_number"] == "B-2025-042"
        # Confidence for bike_number should be 1.0
        assert saved_app["field_confidence"]["children[0].bike_number"] == Decimal("1.0")
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_assign_bike_number_second_child(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {
            "children_updates": [
                {"child_id": "child-002", "bike_number": "B-2025-099"}
            ]
        }
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        child = saved_app["children"][1]
        assert child["bike_number"] == "B-2025-099"
        assert saved_app["field_confidence"]["children[1].bike_number"] == Decimal("1.0")
        del os.environ["DOCUMENTS_BUCKET"]


class TestDrawingKeywordsEditing:
    """Tests for drawing keywords editing (Requirement 5.9, 5.11)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_edit_drawing_keywords(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        new_keywords = ["red", "BMX", "bell", "water bottle"]
        body = {
            "children_updates": [
                {"child_id": "child-001", "drawing_keywords": new_keywords}
            ]
        }
        event = _make_event(body=body)
        result = handler(event, None)
        body_resp = json.loads(result["body"])

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        child = saved_app["children"][0]
        assert child["drawing_keywords"] == new_keywords
        assert saved_app["field_confidence"]["children[0].drawing_keywords"] == Decimal("1.0")
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_edit_dream_bike_description(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {
            "children_updates": [
                {"child_id": "child-001", "dream_bike_description": "A red BMX with a bell"}
            ]
        }
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        child = saved_app["children"][0]
        assert child["dream_bike_description"] == "A red BMX with a bell"
        assert saved_app["field_confidence"]["children[0].dream_bike_description"] == Decimal("1.0")
        del os.environ["DOCUMENTS_BUCKET"]


class TestVersionRetention:
    """Tests for version retention in S3 (Requirement 9.2)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_previous_version_saved_to_s3(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "my-docs-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3_client = MagicMock()
        mock_s3.return_value = mock_s3_client

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        # S3 put_object should have been called with the version key
        mock_s3_client.put_object.assert_called_once()
        s3_call = mock_s3_client.put_object.call_args
        assert s3_call[1]["Bucket"] == "my-docs-bucket"
        assert s3_call[1]["Key"] == "versions/2025/APP001/v2.json"
        assert s3_call[1]["ContentType"] == "application/json"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_previous_versions_s3_key_updated(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"status": "manually_approved"}
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        put_call = mock_tbl.put_item.call_args
        saved_app = put_call[1]["Item"]
        assert saved_app["previous_versions_s3_key"] == "versions/2025/APP001/v2.json"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_previous_version_body_contains_original_data(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "my-docs-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3_client = MagicMock()
        mock_s3.return_value = mock_s3_client

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        s3_call = mock_s3_client.put_object.call_args
        saved_body = json.loads(s3_call[1]["Body"])
        # The saved version should contain the ORIGINAL phone before the edit
        assert saved_body["parent_guardian"]["phone"] == "208-555-0101"
        assert saved_body["application_id"] == "APP001"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_s3_save_failure_returns_500(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3_client = MagicMock()
        mock_s3_client.put_object.side_effect = Exception("S3 error")
        mock_s3.return_value = mock_s3_client

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 500
        body_resp = json.loads(result["body"])
        assert "previous version" in body_resp["error"].lower()
        del os.environ["DOCUMENTS_BUCKET"]


class TestAuditLogging:
    """Tests for audit log recording with field details (Requirement 15.3)."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_audit_log_records_field_changes(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        mock_audit.assert_called_once()
        audit_call = mock_audit.call_args
        assert audit_call[1]["action_type"] == "update"
        assert audit_call[1]["resource_type"] == "application"
        assert audit_call[1]["resource_id"] == "APP001"
        details = audit_call[1]["details"]
        changes = details["changes"]
        assert len(changes) == 1
        assert changes[0]["field_name"] == "parent_guardian.phone"
        assert changes[0]["previous_value"] == "208-555-0101"
        assert changes[0]["new_value"] == "208-555-9999"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_audit_log_records_children_changes(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {
            "children_updates": [
                {"child_id": "child-001", "bike_number": "B-2025-042"}
            ]
        }
        event = _make_event(body=body)
        result = handler(event, None)

        assert result["statusCode"] == 200
        mock_audit.assert_called_once()
        details = mock_audit.call_args[1]["details"]
        changes = details["changes"]
        bike_change = [c for c in changes if "bike_number" in c["field_name"]][0]
        assert bike_change["field_name"] == "children.child-001.bike_number"
        assert bike_change["previous_value"] is None
        assert bike_change["new_value"] == "B-2025-042"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context", side_effect=Exception("Audit error"))
    def test_audit_failure_does_not_break_response(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"status": "manually_approved"}
        event = _make_event(body=body)
        result = handler(event, None)

        # Should still return 200 even if audit logging fails
        assert result["statusCode"] == 200
        del os.environ["DOCUMENTS_BUCKET"]


class TestNotFound:
    """Tests for application not found."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_returns_404_when_not_found(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {}
        mock_table.return_value = mock_tbl

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event("2025", "NONEXISTENT", body=body)
        result = handler(event, None)

        assert result["statusCode"] == 404
        body_resp = json.loads(result["body"])
        assert "not found" in body_resp["error"].lower()


class TestMissingParameters:
    """Tests for missing path parameters and bad requests."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_missing_giveaway_year_returns_400(self, mock_auth):
        from handler import handler

        event = {
            "pathParameters": {"application_id": "APP001"},
            "headers": {"Authorization": "Bearer fake-token"},
            "body": json.dumps({"status": "manually_approved"}),
        }
        result = handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "missing" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_missing_application_id_returns_400(self, mock_auth):
        from handler import handler

        event = {
            "pathParameters": {"giveaway_year": "2025"},
            "headers": {"Authorization": "Bearer fake-token"},
            "body": json.dumps({"status": "manually_approved"}),
        }
        result = handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "missing" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_null_path_parameters_returns_400(self, mock_auth):
        from handler import handler

        event = {
            "pathParameters": None,
            "headers": {"Authorization": "Bearer fake-token"},
            "body": json.dumps({"status": "manually_approved"}),
        }
        result = handler(event, None)

        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_missing_body_returns_400(self, mock_auth):
        from handler import handler

        event = _make_event("2025", "APP001", body=None)
        event["body"] = None
        result = handler(event, None)

        assert result["statusCode"] == 400

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_no_updates_provided_returns_400(self, mock_table, mock_auth):
        from handler import handler

        body = {}
        event = _make_event("2025", "APP001", body=body)
        result = handler(event, None)

        assert result["statusCode"] == 400
        body_resp = json.loads(result["body"])
        assert "no updates" in body_resp["error"].lower()


class TestErrorHandling:
    """Tests for DynamoDB and general error handling."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_dynamodb_fetch_error_returns_500(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.get_item.side_effect = Exception("DynamoDB error")
        mock_table.return_value = mock_tbl

        body = {"field_updates": {"parent_guardian.phone": "208-555-9999"}}
        event = _make_event("2025", "APP001", body=body)
        result = handler(event, None)

        assert result["statusCode"] == 500
        body_resp = json.loads(result["body"])
        assert "retrieve" in body_resp["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_dynamodb_put_error_returns_500(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_tbl.put_item.side_effect = Exception("DynamoDB write error")
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"status": "manually_approved"}
        event = _make_event("2025", "APP001", body=body)
        result = handler(event, None)

        assert result["statusCode"] == 500
        body_resp = json.loads(result["body"])
        assert "update" in body_resp["error"].lower()
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_s3_client")
    @patch("handler.log_audit_from_context")
    def test_cors_headers_present(self, mock_audit, mock_s3, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl
        mock_s3.return_value = MagicMock()

        body = {"status": "manually_approved"}
        event = _make_event(body=body)
        result = handler(event, None)

        assert "Access-Control-Allow-Origin" in result["headers"]
        del os.environ["DOCUMENTS_BUCKET"]
