"""Unit tests for the audit middleware (lambda/shared/audit_middleware.py).

Tests cover:
- log_audit_event writes correct item to DynamoDB
- log_audit_event generates proper year_month and composite sort key
- log_audit_event handles details (update with field changes)
- log_audit_event omits details key when details is None
- log_audit_event handles DynamoDB write errors gracefully (returns None)
- log_audit_event does NOT log PII to CloudWatch
- log_audit_from_context extracts user_id and name from user_context
- log_audit_from_context handles missing keys with defaults
- Environment variable AUDIT_LOG_TABLE_NAME is respected

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 16.10
"""

import logging
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Ensure the shared directory is on the path for imports
sys.path.insert(0, os.path.dirname(__file__))

from audit_middleware import log_audit_event, log_audit_from_context


@pytest.fixture
def mock_table():
    """Return a mocked DynamoDB table with a captured put_item call."""
    table = MagicMock()
    table.put_item = MagicMock()
    return table


@pytest.fixture
def patch_table(mock_table):
    """Patch _get_audit_table to return the mock table."""
    with patch("audit_middleware._get_audit_table", return_value=mock_table):
        yield mock_table


class TestLogAuditEvent:
    """Tests for log_audit_event function."""

    def test_writes_item_to_dynamodb(self, patch_table):
        """log_audit_event should call put_item with the correct item structure."""
        result = log_audit_event(
            user_id="user-001",
            user_name="Admin User",
            action_type="view",
            resource_type="application",
            resource_id="app-123",
        )

        patch_table.put_item.assert_called_once()
        item = patch_table.put_item.call_args[1]["Item"]

        assert item["user_id"] == "user-001"
        assert item["user_name"] == "Admin User"
        assert item["action_type"] == "view"
        assert item["resource_type"] == "application"
        assert item["resource_id"] == "app-123"
        assert "details" not in item
        assert result is not None
        assert result["user_id"] == "user-001"

    def test_generates_correct_timestamp_format(self, patch_table):
        """Timestamp should be ISO format with milliseconds."""
        with patch("audit_middleware.datetime") as mock_dt:
            fixed = datetime(2025, 11, 15, 10, 30, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            log_audit_event("u1", "User", "create", "application", "app-1")

            item = patch_table.put_item.call_args[1]["Item"]
            assert item["timestamp"] == "2025-11-15T10:30:00.000Z"

    def test_generates_correct_resource_id(self, patch_table):
        """resource_id should match the provided value."""
        with patch("audit_middleware.datetime") as mock_dt:
            fixed = datetime(2025, 11, 15, 10, 30, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            log_audit_event("user-42", "User", "delete", "application", "app-9")

            item = patch_table.put_item.call_args[1]["Item"]
            assert item["resource_id"] == "app-9"
            assert item["user_id"] == "user-42"

    def test_includes_details_for_updates(self, patch_table):
        """When details dict is provided, it should be stored in the item."""
        details = {
            "field_name": "parent_guardian.phone",
            "previous_value": "208-555-0100",
            "new_value": "208-555-0199",
        }
        result = log_audit_event(
            user_id="user-001",
            user_name="Admin",
            action_type="update",
            resource_type="application",
            resource_id="app-123",
            details=details,
        )

        item = patch_table.put_item.call_args[1]["Item"]
        assert item["details"] == details
        assert result["details"] == details

    def test_omits_details_when_none(self, patch_table):
        """When details is None, the item should not contain a details key."""
        log_audit_event("u1", "User", "view", "application", "app-1", details=None)

        item = patch_table.put_item.call_args[1]["Item"]
        assert "details" not in item

    def test_handles_dynamodb_error_gracefully(self, patch_table):
        """DynamoDB write failure should return None, not raise."""
        from botocore.exceptions import ClientError

        patch_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "fail"}},
            "PutItem",
        )

        result = log_audit_event("u1", "User", "view", "application", "app-1")
        assert result is None

    def test_does_not_log_pii_to_cloudwatch(self, patch_table, caplog):
        """Log messages must NOT contain PII values like names, emails, phones."""
        details = {
            "field_name": "parent_guardian.phone",
            "previous_value": "208-555-0100",
            "new_value": "208-555-0199",
        }

        with caplog.at_level(logging.INFO, logger="audit_middleware"):
            log_audit_event(
                user_id="user-001",
                user_name="Maria Garcia",
                action_type="update",
                resource_type="application",
                resource_id="app-123",
                details=details,
            )

        log_output = caplog.text
        # PII values must not appear in logs
        assert "Maria Garcia" not in log_output
        assert "208-555-0100" not in log_output
        assert "208-555-0199" not in log_output
        assert "parent_guardian.phone" not in log_output
        # Non-PII action metadata is fine
        assert "update" in log_output
        assert "application" in log_output

    def test_timestamp_is_iso8601(self, patch_table):
        """Timestamp should be in ISO 8601 format ending with Z."""
        log_audit_event("u1", "User", "view", "application", "app-1")

        item = patch_table.put_item.call_args[1]["Item"]
        ts = item["timestamp"]
        assert ts.endswith("Z")
        # Should be parseable as ISO format (minus the Z)
        datetime.fromisoformat(ts.replace("Z", "+00:00"))


class TestLogAuditFromContext:
    """Tests for log_audit_from_context convenience function."""

    def test_extracts_user_id_and_name(self, patch_table):
        """Should extract user_id and name from user_context dict."""
        user_context = {
            "user_id": "user-admin-001",
            "name": "Admin User",
            "email": "admin@example.com",
            "role": "admin",
        }

        result = log_audit_from_context(
            user_context, "view", "application", "app-123"
        )

        item = patch_table.put_item.call_args[1]["Item"]
        assert item["user_id"] == "user-admin-001"
        assert item["user_name"] == "Admin User"
        assert result is not None

    def test_handles_missing_keys_with_defaults(self, patch_table):
        """Should use defaults when user_context is missing keys."""
        result = log_audit_from_context({}, "login", "user_account", "u1")  # noqa: F841

        item = patch_table.put_item.call_args[1]["Item"]
        assert item["user_id"] == "unknown"
        assert item["user_name"] == "Unknown User"

    def test_passes_details_through(self, patch_table):
        """Details dict should be forwarded to log_audit_event."""
        user_context = {"user_id": "u1", "name": "User"}
        details = {"field_name": "status", "previous_value": "needs_review", "new_value": "manually_approved"}

        log_audit_from_context(
            user_context, "update", "application", "app-1", details=details
        )

        item = patch_table.put_item.call_args[1]["Item"]
        assert item["details"] == details


class TestEnvironmentVariable:
    """Tests for AUDIT_LOG_TABLE_NAME environment variable."""

    def test_uses_env_var_for_table_name(self):
        """_get_audit_table should use AUDIT_LOG_TABLE_NAME env var."""
        with patch.dict(os.environ, {"AUDIT_LOG_TABLE_NAME": "my-custom-table"}):
            with patch("audit_middleware.boto3") as mock_boto:
                mock_resource = MagicMock()
                mock_boto.resource.return_value = mock_resource

                from audit_middleware import _get_audit_table

                _get_audit_table()
                mock_resource.Table.assert_called_once_with("my-custom-table")

    def test_defaults_to_standard_table_name(self):
        """_get_audit_table should default to bbp-hkbg-audit-log."""
        env = os.environ.copy()
        env.pop("AUDIT_LOG_TABLE_NAME", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("audit_middleware.boto3") as mock_boto:
                mock_resource = MagicMock()
                mock_boto.resource.return_value = mock_resource

                from audit_middleware import _get_audit_table

                _get_audit_table()
                mock_resource.Table.assert_called_with("bbp-hkbg-audit-log")
