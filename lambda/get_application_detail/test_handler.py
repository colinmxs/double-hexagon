"""Unit tests for get_application_detail Lambda handler.

Tests cover:
- Successful retrieval with all fields (Requirement 5.4, 9.1, 9.2)
- Pre-signed URL generation for documents and drawings (Requirement 5.6)
- Audit log entry recorded on view (Requirement 15.2)
- Application not found returns 404
- Missing path parameters returns 400
- Error handling

Requirements: 5.4, 5.6, 9.1, 9.2, 15.2
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


def _admin_context():
    return {
        "user_id": "admin-001",
        "email": "admin@test.com",
        "name": "Admin User",
        "role": "admin",
        "authorized_giveaway_years": [],
        "status": "active",
    }


def _make_event(giveaway_year="2025", application_id="APP001"):
    """Build an API Gateway proxy event with path parameters."""
    path_params = {}
    if giveaway_year is not None:
        path_params["giveaway_year"] = giveaway_year
    if application_id is not None:
        path_params["application_id"] = application_id
    return {
        "pathParameters": path_params if path_params else None,
        "headers": {"Authorization": "Bearer fake-token"},
    }


def _make_full_application(app_id="APP001", giveaway_year="2025"):
    """Build a complete application record matching the DynamoDB schema."""
    return {
        "giveaway_year": giveaway_year,
        "application_id": app_id,
        "submission_timestamp": "2025-11-15T10:30:00Z",
        "source_type": "upload",
        "status": "needs_review",
        "overall_confidence_score": Decimal("0.72"),
        "confidence_threshold": Decimal("0.80"),
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
            }
        ],
        "field_confidence": {
            "referring_agency.agency_name": Decimal("0.95"),
            "referring_agency.contact_name": Decimal("0.88"),
            "parent_guardian.first_name": Decimal("0.93"),
            "parent_guardian.last_name": Decimal("0.85"),
            "children[0].first_name": Decimal("0.90"),
            "children[0].height_inches": Decimal("0.78"),
        },
        "original_documents": [
            {
                "s3_key": "uploads/2025/APP001/page1.pdf",
                "upload_timestamp": "2025-11-15T10:29:00Z",
                "page_count": Decimal("3"),
            }
        ],
        "version": Decimal("1"),
    }


class TestSuccessfulRetrieval:
    """Tests for successful application detail retrieval."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context")
    def test_returns_full_application(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])

        assert result["statusCode"] == 200
        application = body["application"]
        assert application["application_id"] == "APP001"
        assert application["giveaway_year"] == "2025"
        assert application["status"] == "needs_review"
        assert application["source_type"] == "upload"

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context")
    def test_returns_all_nested_fields(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])
        application = body["application"]

        # Referring agency
        assert application["referring_agency"]["agency_name"] == "Partner Org"
        # Parent/guardian
        assert application["parent_guardian"]["first_name"] == "Maria"
        assert application["parent_guardian"]["preferred_contact_method"] == "WhatsApp"
        # Children
        assert len(application["children"]) == 1
        child = application["children"][0]
        assert child["first_name"] == "Carlos"
        assert child["height_inches"] == 48
        assert child["drawing_keywords"] == ["blue", "mountain bike", "streamers"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context")
    def test_returns_field_confidence_map(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])
        fc = body["application"]["field_confidence"]

        assert fc["referring_agency.agency_name"] == 0.95
        assert fc["children[0].height_inches"] == 0.78

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context")
    def test_decimal_values_converted(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])
        application = body["application"]

        # Decimal integers should be int
        assert isinstance(application["children"][0]["height_inches"], int)
        assert isinstance(application["version"], int)
        # Decimal floats should be float
        assert isinstance(application["overall_confidence_score"], float)


class TestPresignedUrls:
    """Tests for pre-signed URL generation for documents and drawings."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_presigned_get_url", return_value="https://s3.example.com/signed-url")
    @patch("handler.log_audit_from_context")
    def test_document_presigned_urls_generated(self, mock_audit, mock_presign, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])

        doc = body["application"]["original_documents"][0]
        assert doc["presigned_url"] == "https://s3.example.com/signed-url"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_presigned_get_url", return_value="https://s3.example.com/drawing-url")
    @patch("handler.log_audit_from_context")
    def test_drawing_presigned_urls_generated(self, mock_audit, mock_presign, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])

        child = body["application"]["children"][0]
        assert child["drawing_image_url"] == "https://s3.example.com/drawing-url"
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_presigned_get_url")
    @patch("handler.log_audit_from_context")
    def test_presigned_url_called_with_correct_bucket_and_key(self, mock_audit, mock_presign, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "my-docs-bucket"
        mock_presign.return_value = "https://signed.url"
        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        handler(event, None)

        # Should be called for the document and the drawing
        calls = mock_presign.call_args_list
        assert len(calls) == 2
        # Document call
        assert calls[0][0] == ("my-docs-bucket", "uploads/2025/APP001/page1.pdf")
        # Drawing call
        assert calls[1][0] == ("my-docs-bucket", "drawings/2025/APP001/child-001.png")
        del os.environ["DOCUMENTS_BUCKET"]

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context")
    def test_no_presigned_urls_when_no_bucket(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        os.environ.pop("DOCUMENTS_BUCKET", None)
        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])

        doc = body["application"]["original_documents"][0]
        assert "presigned_url" not in doc

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_presigned_get_url", side_effect=Exception("S3 error"))
    @patch("handler.log_audit_from_context")
    def test_presigned_url_failure_returns_null(self, mock_audit, mock_presign, mock_table, mock_auth):
        from handler import handler

        os.environ["DOCUMENTS_BUCKET"] = "test-bucket"
        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)
        body = json.loads(result["body"])

        doc = body["application"]["original_documents"][0]
        assert doc["presigned_url"] is None
        child = body["application"]["children"][0]
        assert child["drawing_image_url"] is None
        del os.environ["DOCUMENTS_BUCKET"]


class TestAuditLogging:
    """Tests for audit log entry on view action."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context")
    def test_audit_log_recorded_on_view(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)

        assert result["statusCode"] == 200
        mock_audit.assert_called_once_with(
            user_context=_admin_context(),
            action_type="view",
            resource_type="application",
            resource_id="APP001",
        )

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context", side_effect=Exception("Audit error"))
    def test_audit_failure_does_not_break_response(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)

        # Should still return 200 even if audit logging fails
        assert result["statusCode"] == 200


class TestNotFound:
    """Tests for application not found."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_returns_404_when_not_found(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "NONEXISTENT")
        result = handler(event, None)

        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert "not found" in body["error"].lower()


class TestMissingParameters:
    """Tests for missing path parameters."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    def test_missing_giveaway_year_returns_400(self, mock_auth):
        from handler import handler

        event = {
            "pathParameters": {"application_id": "APP001"},
            "headers": {"Authorization": "Bearer fake-token"},
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
        }
        result = handler(event, None)

        assert result["statusCode"] == 400


class TestErrorHandling:
    """Tests for DynamoDB and general error handling."""

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    def test_dynamodb_error_returns_500(self, mock_table, mock_auth):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.get_item.side_effect = Exception("DynamoDB error")
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "retrieve" in body["error"].lower()

    @patch(AUTH_PATCH, return_value=_admin_context())
    @patch("handler.get_dynamodb_table")
    @patch("handler.log_audit_from_context")
    def test_cors_headers_present(self, mock_audit, mock_table, mock_auth):
        from handler import handler

        app = _make_full_application()
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {"Item": app}
        mock_table.return_value = mock_tbl

        event = _make_event("2025", "APP001")
        result = handler(event, None)

        assert "Access-Control-Allow-Origin" in result["headers"]
