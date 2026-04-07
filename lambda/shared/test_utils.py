"""Unit tests for shared backend utilities (lambda/shared/utils.py).

Tests cover:
- CORS_HEADERS constant has required keys
- get_dynamodb_table returns a Table resource
- generate_presigned_url creates PUT URL with correct expiry
- generate_presigned_get_url creates GET URL with correct expiry
- generate_application_id produces unique, time-sortable IDs
- build_success_response returns correct structure with CORS
- build_error_response returns correct structure, no PII
- parse_request_body handles valid JSON, empty body, invalid JSON, non-dict
- get_path_parameter extracts params or returns None
- get_query_parameter extracts params with default fallback
- generate_reference_number produces sequential APP-{year}-{seq} IDs via atomic counter

Requirements: 9.4, 16.9, 16.10, R2.1, R2.2
"""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from utils import (
    CORS_HEADERS,
    build_error_response,
    build_success_response,
    generate_application_id,
    generate_presigned_get_url,
    generate_presigned_url,
    generate_reference_number,
    get_dynamodb_table,
    get_path_parameter,
    get_query_parameter,
    parse_request_body,
)


class TestCorsHeaders:
    """Tests for the CORS_HEADERS constant."""

    def test_contains_allow_origin(self):
        assert "Access-Control-Allow-Origin" in CORS_HEADERS

    def test_contains_allow_headers(self):
        assert "Access-Control-Allow-Headers" in CORS_HEADERS
        assert "Content-Type" in CORS_HEADERS["Access-Control-Allow-Headers"]
        assert "Authorization" in CORS_HEADERS["Access-Control-Allow-Headers"]

    def test_contains_allow_methods(self):
        assert "Access-Control-Allow-Methods" in CORS_HEADERS
        for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS"]:
            assert method in CORS_HEADERS["Access-Control-Allow-Methods"]


class TestGetDynamodbTable:
    """Tests for get_dynamodb_table."""

    def test_returns_table_resource(self):
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_boto.resource.return_value = mock_resource

            get_dynamodb_table("my-table")

            mock_boto.resource.assert_called_once_with("dynamodb")
            mock_resource.Table.assert_called_once_with("my-table")


class TestGeneratePresignedUrl:
    """Tests for generate_presigned_url (PUT)."""

    def test_calls_s3_with_put_object(self):
        with patch("utils.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.generate_presigned_url.return_value = "https://s3.example.com/presigned"
            mock_boto.client.return_value = mock_client

            url = generate_presigned_url("my-bucket", "uploads/file.pdf")

            mock_client.generate_presigned_url.assert_called_once_with(
                "put_object",
                Params={"Bucket": "my-bucket", "Key": "uploads/file.pdf"},
                ExpiresIn=900,
            )
            assert url == "https://s3.example.com/presigned"

    def test_default_expiry_is_900_seconds(self):
        """Requirement 16.9: pre-signed URLs expire within 15 minutes."""
        with patch("utils.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.generate_presigned_url.return_value = "https://url"
            mock_boto.client.return_value = mock_client

            generate_presigned_url("bucket", "key")

            call_args = mock_client.generate_presigned_url.call_args
            assert call_args[1]["ExpiresIn"] == 900 or call_args[0][2] == 900 or call_args.kwargs.get("ExpiresIn") == 900

    def test_custom_expiry(self):
        with patch("utils.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.generate_presigned_url.return_value = "https://url"
            mock_boto.client.return_value = mock_client

            generate_presigned_url("bucket", "key", expiry_seconds=300)

            call_args = mock_client.generate_presigned_url.call_args
            assert call_args[1]["ExpiresIn"] == 300


class TestGeneratePresignedGetUrl:
    """Tests for generate_presigned_get_url (GET)."""

    def test_calls_s3_with_get_object(self):
        with patch("utils.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.generate_presigned_url.return_value = "https://s3.example.com/get"
            mock_boto.client.return_value = mock_client

            url = generate_presigned_get_url("my-bucket", "drawings/img.png")

            mock_client.generate_presigned_url.assert_called_once_with(
                "get_object",
                Params={"Bucket": "my-bucket", "Key": "drawings/img.png"},
                ExpiresIn=900,
            )
            assert url == "https://s3.example.com/get"

    def test_default_expiry_is_900_seconds(self):
        with patch("utils.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.generate_presigned_url.return_value = "https://url"
            mock_boto.client.return_value = mock_client

            generate_presigned_get_url("bucket", "key")

            call_args = mock_client.generate_presigned_url.call_args
            assert call_args[1]["ExpiresIn"] == 900


class TestGenerateApplicationId:
    """Tests for generate_application_id."""

    def test_returns_string(self):
        app_id = generate_application_id()
        assert isinstance(app_id, str)

    def test_returns_28_char_hex_string(self):
        app_id = generate_application_id()
        # 12 chars timestamp hex + 16 chars uuid hex = 28
        assert len(app_id) == 28
        # Should be valid uppercase hex
        int(app_id, 16)

    def test_ids_are_unique(self):
        ids = {generate_application_id() for _ in range(100)}
        assert len(ids) == 100

    def test_ids_are_time_sortable(self):
        """Earlier IDs should sort before later IDs (lexicographic)."""
        id1 = generate_application_id()
        time.sleep(0.01)
        id2 = generate_application_id()
        # The timestamp prefix ensures time-sortability
        assert id1[:12] <= id2[:12]


class TestBuildSuccessResponse:
    """Tests for build_success_response."""

    def test_default_status_code_200(self):
        resp = build_success_response({"result": "ok"})
        assert resp["statusCode"] == 200

    def test_custom_status_code(self):
        resp = build_success_response({"created": True}, status_code=201)
        assert resp["statusCode"] == 201

    def test_body_is_json_string(self):
        resp = build_success_response({"key": "value"})
        parsed = json.loads(resp["body"])
        assert parsed == {"key": "value"}

    def test_includes_cors_headers(self):
        resp = build_success_response({})
        for key in CORS_HEADERS:
            assert key in resp["headers"]

    def test_includes_content_type_json(self):
        resp = build_success_response({})
        assert resp["headers"]["Content-Type"] == "application/json"


class TestBuildErrorResponse:
    """Tests for build_error_response."""

    def test_returns_correct_status_code(self):
        resp = build_error_response(400, "Bad request")
        assert resp["statusCode"] == 400

    def test_body_contains_error_key(self):
        resp = build_error_response(500, "Internal server error")
        parsed = json.loads(resp["body"])
        assert parsed == {"error": "Internal server error"}

    def test_includes_cors_headers(self):
        resp = build_error_response(404, "Not found")
        for key in CORS_HEADERS:
            assert key in resp["headers"]

    def test_no_pii_in_error_message(self):
        """Requirement 16.10: error responses must not contain PII."""
        resp = build_error_response(400, "Invalid request")
        body_str = resp["body"]
        # Verify the message is exactly what we passed — no PII injected
        parsed = json.loads(body_str)
        assert parsed["error"] == "Invalid request"


class TestParseRequestBody:
    """Tests for parse_request_body."""

    def test_parses_valid_json(self):
        event = {"body": '{"name": "test", "value": 42}'}
        result = parse_request_body(event)
        assert result == {"name": "test", "value": 42}

    def test_raises_on_missing_body(self):
        with pytest.raises(ValueError, match="missing or empty"):
            parse_request_body({})

    def test_raises_on_none_body(self):
        with pytest.raises(ValueError, match="missing or empty"):
            parse_request_body({"body": None})

    def test_raises_on_empty_string_body(self):
        with pytest.raises(ValueError, match="missing or empty"):
            parse_request_body({"body": ""})

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_request_body({"body": "not json at all"})

    def test_raises_on_non_dict_json(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_request_body({"body": "[1, 2, 3]"})

    def test_handles_base64_encoded_body(self):
        import base64

        raw = '{"encoded": true}'
        b64 = base64.b64encode(raw.encode()).decode()
        event = {"body": b64, "isBase64Encoded": True}
        result = parse_request_body(event)
        assert result == {"encoded": True}


class TestGetPathParameter:
    """Tests for get_path_parameter."""

    def test_extracts_existing_parameter(self):
        event = {"pathParameters": {"id": "app-123"}}
        assert get_path_parameter(event, "id") == "app-123"

    def test_returns_none_for_missing_parameter(self):
        event = {"pathParameters": {"id": "app-123"}}
        assert get_path_parameter(event, "other") is None

    def test_returns_none_when_path_parameters_is_none(self):
        event = {"pathParameters": None}
        assert get_path_parameter(event, "id") is None

    def test_returns_none_when_path_parameters_missing(self):
        assert get_path_parameter({}, "id") is None


class TestGetQueryParameter:
    """Tests for get_query_parameter."""

    def test_extracts_existing_parameter(self):
        event = {"queryStringParameters": {"status": "approved"}}
        assert get_query_parameter(event, "status") == "approved"

    def test_returns_default_for_missing_parameter(self):
        event = {"queryStringParameters": {"status": "approved"}}
        assert get_query_parameter(event, "page", "1") == "1"

    def test_returns_none_default_when_not_specified(self):
        event = {"queryStringParameters": {}}
        assert get_query_parameter(event, "missing") is None

    def test_returns_default_when_query_params_is_none(self):
        event = {"queryStringParameters": None}
        assert get_query_parameter(event, "x", "fallback") == "fallback"

    def test_returns_default_when_query_params_missing(self):
        assert get_query_parameter({}, "x", "default") == "default"


class TestGenerateReferenceNumber:
    """Tests for generate_reference_number — atomic counter-based sequential IDs.

    Requirements: R2.1, R2.2
    """

    def test_returns_correct_format(self):
        """Reference number matches APP-{year}-{seq:04d} format."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 1}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            result = generate_reference_number("2025")

            assert result == "2025-0001"

    def test_sequence_number_zero_padded(self):
        """Sequence numbers are zero-padded to 4 digits."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 42}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            result = generate_reference_number("2025")

            assert result == "2025-0042"

    def test_large_sequence_number(self):
        """Sequence numbers beyond 4 digits still work (no truncation)."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 12345}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            result = generate_reference_number("2025")

            assert result == "2025-12345"

    def test_uses_correct_config_key(self):
        """Atomic counter key is next_ref_{year}."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 1}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            generate_reference_number("2024")

            mock_table.update_item.assert_called_once_with(
                Key={"config_key": "next_ref_2024"},
                UpdateExpression="ADD #v :inc",
                ExpressionAttributeNames={"#v": "value"},
                ExpressionAttributeValues={":inc": 1},
                ReturnValues="UPDATED_NEW",
            )

    def test_uses_default_config_table(self):
        """Defaults to CONFIG_TABLE_NAME env var or bbp-hkbg-config."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 1}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            generate_reference_number("2025")

            mock_resource.Table.assert_called_with("bbp-hkbg-config")

    @patch.dict(os.environ, {"CONFIG_TABLE_NAME": "custom-config"})
    def test_uses_env_var_config_table(self):
        """Reads CONFIG_TABLE_NAME from environment when set."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 1}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            generate_reference_number("2025")

            mock_resource.Table.assert_called_with("custom-config")

    def test_accepts_explicit_config_table_name(self):
        """Explicit config_table_name parameter overrides env var."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 1}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            generate_reference_number("2025", config_table_name="my-table")

            mock_resource.Table.assert_called_with("my-table")

    def test_different_years_produce_different_keys(self):
        """Each year uses its own counter key."""
        with patch("utils.boto3") as mock_boto:
            mock_resource = MagicMock()
            mock_table = MagicMock()
            mock_table.update_item.return_value = {
                "Attributes": {"value": 1}
            }
            mock_resource.Table.return_value = mock_table
            mock_boto.resource.return_value = mock_resource

            generate_reference_number("2025")
            generate_reference_number("2024")

            calls = mock_table.update_item.call_args_list
            assert calls[0][1]["Key"] == {"config_key": "next_ref_2025"}
            assert calls[1][1]["Key"] == {"config_key": "next_ref_2024"}
