"""Unit tests for generate_presigned_url Lambda handler.

Tests cover:
- File type validation: PDF, PNG, JPEG accepted; others rejected (Requirement 2.1)
- File size validation: ≤10MB accepted; over 10MB rejected (Requirement 2.2, 2.7)
- Pre-signed URL generation with 15-minute expiry (Requirement 2.3, 16.9)
- Reference identifier returned on success
- Required field validation (file_name, file_type, file_size)
- Active giveaway year fetched from Config table
- S3 key follows pattern: uploads/{giveaway_year}/{reference_id}/{filename}
- Error handling for Config table and S3 failures

Requirements: 2.1, 2.2, 2.3, 2.7, 16.9
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
    """Return a minimal valid presign request body."""
    return {
        "file_name": "application.pdf",
        "file_type": "application/pdf",
        "file_size": 1024,
    }


class TestFieldValidation:
    """Tests for required field validation."""

    def test_missing_body_returns_400(self):
        from handler import handler

        resp = handler({"body": None}, None)
        assert resp["statusCode"] == 400

    def test_invalid_json_returns_400(self):
        from handler import handler

        resp = handler({"body": "not json"}, None)
        assert resp["statusCode"] == 400

    def test_missing_file_name_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["file_name"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "file_name" in json.loads(resp["body"])["error"]

    def test_empty_file_name_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["file_name"] = "   "
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "file_name" in json.loads(resp["body"])["error"]

    def test_missing_file_type_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["file_type"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "file_type" in json.loads(resp["body"])["error"]

    def test_missing_file_size_returns_400(self):
        from handler import handler

        body = _valid_body()
        del body["file_size"]
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "file_size" in json.loads(resp["body"])["error"]

    def test_non_numeric_file_size_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["file_size"] = "not_a_number"
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        assert "file_size" in json.loads(resp["body"])["error"]

    def test_zero_file_size_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["file_size"] = 0
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400

    def test_negative_file_size_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["file_size"] = -100
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400


class TestFileTypeValidation:
    """Tests for file type validation (Requirement 2.1)."""

    def test_pdf_accepted(self):
        from handler import handler

        body = _valid_body()
        body["file_type"] = "application/pdf"
        with patch("handler._get_active_giveaway_year", return_value="2025"), \
             patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned"):
            resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 200

    def test_png_accepted(self):
        from handler import handler

        body = _valid_body()
        body["file_type"] = "image/png"
        body["file_name"] = "photo.png"
        with patch("handler._get_active_giveaway_year", return_value="2025"), \
             patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned"):
            resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 200

    def test_jpeg_accepted(self):
        from handler import handler

        body = _valid_body()
        body["file_type"] = "image/jpeg"
        body["file_name"] = "photo.jpg"
        with patch("handler._get_active_giveaway_year", return_value="2025"), \
             patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned"):
            resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 200

    def test_unsupported_type_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["file_type"] = "application/zip"
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        error = json.loads(resp["body"])["error"]
        assert "Unsupported file type" in error

    def test_text_plain_rejected(self):
        from handler import handler

        body = _valid_body()
        body["file_type"] = "text/plain"
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400


class TestFileSizeValidation:
    """Tests for file size validation (Requirement 2.2, 2.7)."""

    def test_exactly_10mb_accepted(self):
        from handler import handler

        body = _valid_body()
        body["file_size"] = 10 * 1024 * 1024  # exactly 10MB
        with patch("handler._get_active_giveaway_year", return_value="2025"), \
             patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned"):
            resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 200

    def test_over_10mb_returns_400(self):
        from handler import handler

        body = _valid_body()
        body["file_size"] = 10 * 1024 * 1024 + 1  # 10MB + 1 byte
        resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 400
        error = json.loads(resp["body"])["error"]
        assert "10MB" in error

    def test_small_file_accepted(self):
        from handler import handler

        body = _valid_body()
        body["file_size"] = 512
        with patch("handler._get_active_giveaway_year", return_value="2025"), \
             patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned"):
            resp = handler(_make_event(body), None)
        assert resp["statusCode"] == 200


class TestSuccessfulGeneration:
    """Tests for successful pre-signed URL generation."""

    @patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_returns_200_with_upload_url(self, mock_year, mock_presign):
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "upload_url" in body
        assert body["upload_url"] == "https://s3.example.com/presigned"

    @patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_returns_reference_id(self, mock_year, mock_presign):
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        body = json.loads(resp["body"])
        assert "reference_id" in body
        assert len(body["reference_id"]) > 0

    @patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_returns_s3_key(self, mock_year, mock_presign):
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        body = json.loads(resp["body"])
        assert "s3_key" in body
        assert body["s3_key"].startswith("uploads/2025/")
        assert body["s3_key"].endswith("/application.pdf")

    @patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_s3_key_follows_pattern(self, mock_year, mock_presign):
        """S3 key should be uploads/{giveaway_year}/{reference_id}/{filename}."""
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        body = json.loads(resp["body"])
        parts = body["s3_key"].split("/")
        assert parts[0] == "uploads"
        assert parts[1] == "2025"
        assert len(parts[2]) > 0  # reference_id
        assert parts[3] == "application.pdf"

    @patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_presigned_url_called_with_900s_expiry(self, mock_year, mock_presign):
        """Requirement 16.9: pre-signed URL expires in 15 minutes (900 seconds)."""
        from handler import handler

        handler(_make_event(_valid_body()), None)
        mock_presign.assert_called_once()
        call_kwargs = mock_presign.call_args
        assert call_kwargs[1]["expiry_seconds"] == 900 or call_kwargs[0][2] == 900

    @patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_file_name_with_spaces_sanitized(self, mock_year, mock_presign):
        from handler import handler

        body = _valid_body()
        body["file_name"] = "my application form.pdf"
        resp = handler(_make_event(body), None)
        body_resp = json.loads(resp["body"])
        assert " " not in body_resp["s3_key"]
        assert "my_application_form.pdf" in body_resp["s3_key"]

    @patch("handler.generate_presigned_url", return_value="https://s3.example.com/presigned")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_cors_headers_present(self, mock_year, mock_presign):
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        assert "Access-Control-Allow-Origin" in resp["headers"]


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

    @patch("handler.generate_presigned_url", side_effect=Exception("S3 error"))
    @patch("handler._get_active_giveaway_year", return_value="2025")
    def test_s3_presign_failure_returns_500(self, mock_year, mock_presign):
        from handler import handler

        resp = handler(_make_event(_valid_body()), None)
        assert resp["statusCode"] == 500
        assert "upload URL" in json.loads(resp["body"])["error"]
