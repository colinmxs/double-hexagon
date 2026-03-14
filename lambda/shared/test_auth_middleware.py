"""Unit tests for the auth middleware (lambda/shared/auth_middleware.py).

Tests cover:
- AUTH_ENABLED=false returns LOCAL_ADMIN_USER (auth bypass)
- AUTH_ENABLED=true with valid JWT and existing active user returns user context
- AUTH_ENABLED=true with missing Authorization header raises AuthError(401)
- AUTH_ENABLED=true with invalid token format raises AuthError
- AUTH_ENABLED=true with user not found raises AuthError(403)
- AUTH_ENABLED=true with inactive user raises AuthError(403)
- Bearer prefix is stripped correctly
- Lookup by cognito_sub works
- Fallback lookup by email works when cognito_sub lookup fails
- Default AUTH_ENABLED is "true" when env var not set

Requirements: 14.3, 14.6, 14.10
"""

import base64
import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Ensure the shared directory is on the path for imports
sys.path.insert(0, os.path.dirname(__file__))

from auth_middleware import (
    AuthError,
    LOCAL_ADMIN_USER,
    authenticate,
    _decode_jwt_payload,
)


def _make_jwt(payload: dict) -> str:
    """Build a fake JWT (header.payload.signature) with the given payload."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


def _make_user_record(**overrides):
    """Return a DynamoDB user record dict with sensible defaults."""
    record = {
        "user_id": "user-001",
        "cognito_sub": "cognito-sub-123",
        "email": "admin@test.dev",
        "name": "Test Admin",
        "role": "admin",
        "authorized_giveaway_years": ["2025"],
        "status": "active",
    }
    record.update(overrides)
    return record


def _make_event(token=None, bearer=True):
    """Build a minimal API Gateway event with an Authorization header."""
    headers = {}
    if token is not None:
        value = f"Bearer {token}" if bearer else token
        headers["Authorization"] = value
    return {"headers": headers}


# ---------------------------------------------------------------------------
# _decode_jwt_payload
# ---------------------------------------------------------------------------

class TestDecodeJwtPayload:
    def test_decodes_valid_jwt(self):
        payload = {"sub": "abc", "email": "a@b.com"}
        token = _make_jwt(payload)
        result = _decode_jwt_payload(token)
        assert result["sub"] == "abc"
        assert result["email"] == "a@b.com"

    def test_raises_on_invalid_format_no_dots(self):
        with pytest.raises(AuthError, match="Invalid token format"):
            _decode_jwt_payload("not-a-jwt")

    def test_raises_on_two_parts(self):
        with pytest.raises(AuthError, match="Invalid token format"):
            _decode_jwt_payload("part1.part2")


# ---------------------------------------------------------------------------
# authenticate — AUTH_ENABLED=false (bypass)
# ---------------------------------------------------------------------------

class TestAuthBypass:
    """When AUTH_ENABLED=false, authenticate() returns LOCAL_ADMIN_USER."""

    @patch.dict(os.environ, {"AUTH_ENABLED": "false"})
    def test_returns_local_admin_user(self):
        result = authenticate({"headers": {}})
        assert result["user_id"] == LOCAL_ADMIN_USER["user_id"]
        assert result["role"] == "admin"
        assert result["email"] == LOCAL_ADMIN_USER["email"]

    @patch.dict(os.environ, {"AUTH_ENABLED": "false"})
    def test_returns_copy_not_reference(self):
        """Mutating the returned dict must not affect LOCAL_ADMIN_USER."""
        result = authenticate({"headers": {}})
        result["role"] = "reporter"
        assert LOCAL_ADMIN_USER["role"] == "admin"

    @patch.dict(os.environ, {"AUTH_ENABLED": "False"})
    def test_case_insensitive_false(self):
        result = authenticate({"headers": {}})
        assert result["user_id"] == LOCAL_ADMIN_USER["user_id"]

    @patch.dict(os.environ, {"AUTH_ENABLED": "FALSE"})
    def test_uppercase_false(self):
        result = authenticate({"headers": {}})
        assert result["user_id"] == LOCAL_ADMIN_USER["user_id"]


# ---------------------------------------------------------------------------
# authenticate — AUTH_ENABLED=true (default / explicit)
# ---------------------------------------------------------------------------

class TestAuthEnabled:
    """Tests for the full authentication path (AUTH_ENABLED=true)."""

    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_missing_authorization_header_raises_401(self):
        with pytest.raises(AuthError) as exc_info:
            authenticate({"headers": {}})
        assert exc_info.value.status_code == 401
        assert "Missing Authorization header" in str(exc_info.value)

    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_none_headers_raises_401(self):
        with pytest.raises(AuthError) as exc_info:
            authenticate({"headers": None})
        assert exc_info.value.status_code == 401

    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_empty_bearer_token_raises_401(self):
        with pytest.raises(AuthError) as exc_info:
            authenticate({"headers": {"Authorization": "Bearer "}})
        assert exc_info.value.status_code == 401

    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_invalid_token_format_raises_auth_error(self):
        with pytest.raises(AuthError, match="Invalid token format"):
            authenticate({"headers": {"Authorization": "Bearer not-a-jwt"}})

    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_token_missing_sub_and_email_raises_auth_error(self):
        token = _make_jwt({"aud": "some-client"})
        with pytest.raises(AuthError, match="Token missing required claims"):
            authenticate(_make_event(token))

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_valid_jwt_active_user_returns_context(self, mock_table_fn):
        user_record = _make_user_record()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [user_record]}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "cognito-sub-123", "email": "admin@test.dev"})
        result = authenticate(_make_event(token))

        assert result["user_id"] == "user-001"
        assert result["role"] == "admin"
        assert result["email"] == "admin@test.dev"
        assert result["status"] == "active"

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_user_not_found_raises_403(self, mock_table_fn):
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_table.query.return_value = {"Items": []}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "unknown-sub", "email": "nobody@test.dev"})
        with pytest.raises(AuthError) as exc_info:
            authenticate(_make_event(token))
        assert exc_info.value.status_code == 403
        assert "User not found" in str(exc_info.value)

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_inactive_user_raises_403(self, mock_table_fn):
        user_record = _make_user_record(status="inactive")
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [user_record]}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "cognito-sub-123", "email": "admin@test.dev"})
        with pytest.raises(AuthError) as exc_info:
            authenticate(_make_event(token))
        assert exc_info.value.status_code == 403
        assert "inactive" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Bearer prefix stripping & lookup strategies
# ---------------------------------------------------------------------------

class TestBearerAndLookup:
    """Tests for Bearer prefix handling and cognito_sub / email fallback."""

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_bearer_prefix_stripped(self, mock_table_fn):
        user_record = _make_user_record()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [user_record]}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "cognito-sub-123", "email": "admin@test.dev"})
        event = {"headers": {"Authorization": f"Bearer {token}"}}
        result = authenticate(event)
        assert result["user_id"] == "user-001"

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_token_without_bearer_prefix_works(self, mock_table_fn):
        user_record = _make_user_record()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [user_record]}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "cognito-sub-123", "email": "admin@test.dev"})
        event = {"headers": {"Authorization": token}}
        result = authenticate(event)
        assert result["user_id"] == "user-001"

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_lookup_by_cognito_sub(self, mock_table_fn):
        """When cognito_sub lookup succeeds, email lookup is not attempted."""
        user_record = _make_user_record()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [user_record]}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "cognito-sub-123", "email": "admin@test.dev"})
        authenticate(_make_event(token))

        mock_table.scan.assert_called_once()
        mock_table.query.assert_not_called()

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_fallback_to_email_when_sub_not_found(self, mock_table_fn):
        """When cognito_sub lookup fails, falls back to email GSI lookup."""
        user_record = _make_user_record()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_table.query.return_value = {"Items": [user_record]}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "unknown-sub", "email": "admin@test.dev"})
        result = authenticate(_make_event(token))

        assert result["user_id"] == "user-001"
        mock_table.scan.assert_called_once()
        mock_table.query.assert_called_once()


# ---------------------------------------------------------------------------
# Default AUTH_ENABLED behavior
# ---------------------------------------------------------------------------

class TestDefaultAuthEnabled:
    """When AUTH_ENABLED env var is not set, default should be 'true'."""

    @patch.dict(os.environ, {}, clear=False)
    def test_default_auth_enabled_is_true(self):
        """Without AUTH_ENABLED env var, auth should be enforced."""
        # Remove AUTH_ENABLED if present
        os.environ.pop("AUTH_ENABLED", None)
        with pytest.raises(AuthError) as exc_info:
            authenticate({"headers": {}})
        assert exc_info.value.status_code == 401

    @patch("auth_middleware._get_users_table")
    @patch.dict(os.environ, {"AUTH_ENABLED": "true"})
    def test_lowercase_authorization_header(self, mock_table_fn):
        """API Gateway may normalize header keys to lowercase."""
        user_record = _make_user_record()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [user_record]}
        mock_table_fn.return_value = mock_table

        token = _make_jwt({"sub": "cognito-sub-123", "email": "admin@test.dev"})
        event = {"headers": {"authorization": token}}
        result = authenticate(event)
        assert result["user_id"] == "user-001"
