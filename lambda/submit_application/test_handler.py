"""Unit tests for submit_application Lambda handler.

Tests cover:
- Required field validation (referring_agency, parent_guardian, children)
- Child height_inches mandatory validation (Requirement 1.3)
- Confidence 1.0 assignment for digital submissions (Requirement 1.4)
- Status set to auto_approved for digital submissions
- Active giveaway year read from Config table (Requirement 17.12)
- Audit log entry recorded for create action (Requirement 9.1)
- DynamoDB storage of application record
- Error handling for missing body, invalid JSON, Config table failures

Requirements: 1.3, 1.4, 9.1, 17.12
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))


def _make_event(body_dict):
    """Helper to build an API Gateway proxy event with a JSON body."""
    return {"body": json.dumps(body_dict)}


def _valid_body():
    """Return a minimal valid application body."""
    return {
        "referring_agency": {
            "agency_name": "Test Agency",
            "contact_name": "Jane Doe",
            "contact_phone": "208-555-0100",
            "contact_email": "jane@agency.org",
        },
        "parent_guardian": {
            "first_name": "Maria",
            "last_name": "Garcia",
            "address": "123 Main St",
            "city": "Boise",
            "zip_code": "83702",
            "phone": "208-555-0101",
        },
        "children": [
            {
                "first_name": "Carlos",
                "last_name": "Garcia",
                "height_inches": 48,
            }
        ],
    }


class TestValidation:
    """Tests for required field validation."""

    def test_missing_body_returns_400(self):
        from handler import handler

        resp = handler({"body": None}, None)
        assert resp["statusCode"] == 400

    def test_invalid_json_returns_400(self):
        from handler import handler

        resp = handler({"body": "not json"}, None)
        assert resp["statusCode"] == 400

    def test_missing_referring_agency_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["referring_agency"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "referring_agency" in json.loads(resp["body"])["error"]

    def test_missing_agency_field_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["referring_agency"]["agency_name"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "agency_name" in json.loads(resp["body"])["error"]

    def test_empty_agency_field_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["referring_agency"]["contact_name"] = "   "
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "contact_name" in json.loads(resp["body"])["error"]

    def test_missing_parent_guardian_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["parent_guardian"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "parent_guardian" in json.loads(resp["body"])["error"]

    def test_missing_parent_field_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["parent_guardian"]["first_name"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "first_name" in json.loads(resp["body"])["error"]

    def test_missing_children_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["children"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "child" in json.loads(resp["body"])["error"].lower()

    def test_empty_children_array_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["children"] = []
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400

    def test_missing_child_height_returns_400(self):
        """Requirement 1.3: height_inches is mandatory."""
        from handler import handler

        body = _valid_body()
        del body["children"][0]["height_inches"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "height_inches" in json.loads(resp["body"])["error"]

    def test_invalid_child_height_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["children"][0]["height_inches"] = "not_a_number"
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "height_inches" in json.loads(resp["body"])["error"]

    def test_negative_child_height_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["children"][0]["height_inches"] = -5
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "height_inches" in json.loads(resp["body"])["error"]

    def test_zero_child_height_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["children"][0]["height_inches"] = 0
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400

    def test_missing_child_name_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["children"][0]["first_name"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "first_name" in json.loads(resp["body"])["error"]


class TestSuccessfulSubmission:
    """Tests for successful digital application submission."""

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_returns_201_with_application_id(self, mock_year, mock_table, mock_audit):
        from handler import handler

        mock_table.return_value = MagicMock()
        resp = handler(_make_event(_valid_body()), None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert "application_id" in body
        assert body["status"] == "auto_approved"
        assert body["giveaway_year"] == "2025"

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_stores_record_in_dynamodb(self, mock_year, mock_table, mock_audit):
        """Requirement 1.4: store with confidence 1.0 in DynamoDB."""
        from handler import handler

        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl
        handler(_make_event(_valid_body()), None)

        mock_tbl.put_item.assert_called_once()
        item = mock_tbl.put_item.call_args[1]["Item"]
        assert item["giveaway_year"] == "2025"
        assert item["source_type"] == "digital"
        assert item["status"] == "auto_approved"
        assert item["overall_confidence_score"] == 1.0
        assert item["version"] == 1
        assert item["original_documents"] == []

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_all_field_confidence_values_are_1(self, mock_year, mock_table, mock_audit):
        """Requirement 1.4: all field confidence scores are 1.0 for digital."""
        from handler import handler

        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl
        handler(_make_event(_valid_body()), None)

        item = mock_tbl.put_item.call_args[1]["Item"]
        fc = item["field_confidence"]
        for key, val in fc.items():
            assert val == 1.0, f"field_confidence[{key}] should be 1.0, got {val}"

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_children_get_child_ids(self, mock_year, mock_table, mock_audit):
        from handler import handler

        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl
        body = _valid_body()
        body["children"].append({
            "first_name": "Sofia",
            "last_name": "Garcia",
            "height_inches": 42,
        })
        handler(_make_event(body), None)

        item = mock_tbl.put_item.call_args[1]["Item"]
        assert item["children"][0]["child_id"] == "child-001"
        assert item["children"][1]["child_id"] == "child-002"

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_audit_log_recorded(self, mock_year, mock_table, mock_audit):
        """Requirement 9.1: audit log entry for create action."""
        from handler import handler

        mock_table.return_value = MagicMock()
        resp = handler(_make_event(_valid_body()), None)
        body = json.loads(resp["body"])

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["action_type"] == "create"
        assert call_kwargs["resource_type"] == "application"
        assert call_kwargs["resource_id"] == body["application_id"]
        assert call_kwargs["user_id"] == "public"

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_height_stored_as_number(self, mock_year, mock_table, mock_audit):
        from handler import handler

        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl
        body = _valid_body()
        body["children"][0]["height_inches"] = "48"
        handler(_make_event(body), None)

        item = mock_tbl.put_item.call_args[1]["Item"]
        assert item["children"][0]["height_inches"] == 48.0


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @patch("handler._get_active_giveaway_year", return_value=None)
    def test_no_active_year_returns_500(self, mock_year):
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        assert resp["statusCode"] == 500
        assert "giveaway year" in json.loads(resp["body"])["error"].lower()

    @patch("handler._get_active_giveaway_year", side_effect=Exception("DynamoDB error"))
    def test_config_table_error_returns_500(self, mock_year):
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        assert resp["statusCode"] == 500

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_dynamodb_write_failure_returns_500(self, mock_year, mock_table, mock_audit):
        from handler import handler

        mock_tbl = MagicMock()
        mock_tbl.put_item.side_effect = Exception("Write failed")
        mock_table.return_value = mock_tbl

        resp = handler(_make_event(_valid_body()), None)
        assert resp["statusCode"] == 500
        assert "store" in json.loads(resp["body"])["error"].lower()

    @patch("handler.log_audit_event", side_effect=Exception("Audit failed"))
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_audit_failure_does_not_block_submission(self, mock_year, mock_table, mock_audit):
        from handler import handler

        mock_table.return_value = MagicMock()
        resp = handler(_make_event(_valid_body()), None)
        # Submission should still succeed even if audit logging fails
        assert resp["statusCode"] == 201


class TestMultipleChildren:
    """Tests for multi-child submissions."""

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_multiple_children_all_validated(self, mock_year, mock_table, mock_audit):
        from handler import handler

        body = _valid_body()
        body["children"].append({
            "first_name": "Sofia",
            "last_name": "Garcia",
            # Missing height_inches — should fail
        })
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "height_inches" in json.loads(resp["body"])["error"]

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_multiple_valid_children_succeed(self, mock_year, mock_table, mock_audit):
        from handler import handler

        mock_table.return_value = MagicMock()
        body = _valid_body()
        body["children"].append({
            "first_name": "Sofia",
            "last_name": "Garcia",
            "height_inches": 42,
            "age": 6,
            "gender": "Female",
        })
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 201

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_field_confidence_covers_all_children(self, mock_year, mock_table, mock_audit):
        from handler import handler

        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl
        body = _valid_body()
        body["children"].append({
            "first_name": "Sofia",
            "last_name": "Garcia",
            "height_inches": 42,
        })
        handler(_make_event(body), None)

        item = mock_tbl.put_item.call_args[1]["Item"]
        fc = item["field_confidence"]
        assert "children[0].first_name" in fc
        assert "children[1].first_name" in fc
        assert fc["children[0].first_name"] == 1.0
        assert fc["children[1].first_name"] == 1.0
