"""Unit tests for the RBAC module (lambda/shared/rbac.py).

Tests cover:
- build_error_response: correct status codes, JSON body, CORS headers, no PII
- enforce_year_scoping: admin always allowed, reporter scoped, submitter denied
- require_role: auth integration, role checking, 403 on unauthorized, 401 on auth failure

Requirements: 14.3, 14.6, 14.10
"""

import json
from unittest.mock import patch

import sys
import os

# Ensure the shared directory is on the path for imports
sys.path.insert(0, os.path.dirname(__file__))

from rbac import build_error_response, enforce_year_scoping, require_role
from rbac import AuthError


# ---------------------------------------------------------------------------
# build_error_response
# ---------------------------------------------------------------------------

class TestBuildErrorResponse:
    def test_returns_correct_status_code(self):
        resp = build_error_response(403, "Forbidden")
        assert resp["statusCode"] == 403

    def test_returns_json_body_with_error_key(self):
        resp = build_error_response(401, "Unauthorized")
        body = json.loads(resp["body"])
        assert body == {"error": "Unauthorized"}

    def test_includes_cors_headers(self):
        resp = build_error_response(500, "Internal error")
        headers = resp["headers"]
        assert "Access-Control-Allow-Origin" in headers
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"

    def test_error_message_contains_no_pii(self):
        """Error messages must be generic — no PII (Req 16.10)."""
        resp = build_error_response(403, "Forbidden: insufficient permissions")
        body = json.loads(resp["body"])
        # Should not contain email, name, or user-specific data
        assert "email" not in body["error"].lower()
        assert "@" not in body["error"]


# ---------------------------------------------------------------------------
# enforce_year_scoping
# ---------------------------------------------------------------------------

class TestEnforceYearScoping:
    def test_admin_always_allowed(self):
        ctx = {"role": "admin", "authorized_giveaway_years": []}
        assert enforce_year_scoping(ctx, "2025") is True

    def test_admin_allowed_even_without_years_key(self):
        ctx = {"role": "admin"}
        assert enforce_year_scoping(ctx, "2024") is True

    def test_reporter_allowed_for_authorized_year(self):
        ctx = {"role": "reporter", "authorized_giveaway_years": ["2024", "2025"]}
        assert enforce_year_scoping(ctx, "2025") is True

    def test_reporter_denied_for_unauthorized_year(self):
        ctx = {"role": "reporter", "authorized_giveaway_years": ["2024"]}
        assert enforce_year_scoping(ctx, "2025") is False

    def test_reporter_denied_when_no_years_assigned(self):
        ctx = {"role": "reporter", "authorized_giveaway_years": []}
        assert enforce_year_scoping(ctx, "2025") is False

    def test_reporter_year_comparison_is_string_based(self):
        """Handles integer vs string year values gracefully."""
        ctx = {"role": "reporter", "authorized_giveaway_years": [2025]}
        assert enforce_year_scoping(ctx, "2025") is True
        assert enforce_year_scoping(ctx, 2025) is True

    def test_submitter_always_denied(self):
        ctx = {"role": "submitter", "authorized_giveaway_years": ["2025"]}
        assert enforce_year_scoping(ctx, "2025") is False

    def test_unknown_role_denied(self):
        ctx = {"role": "unknown", "authorized_giveaway_years": ["2025"]}
        assert enforce_year_scoping(ctx, "2025") is False

    def test_empty_role_denied(self):
        ctx = {"role": "", "authorized_giveaway_years": ["2025"]}
        assert enforce_year_scoping(ctx, "2025") is False


# ---------------------------------------------------------------------------
# require_role decorator
# ---------------------------------------------------------------------------

class TestRequireRole:
    """Tests for the require_role decorator."""

    def _make_admin_context(self):
        return {
            "user_id": "user-001",
            "email": "admin@test.dev",
            "name": "Admin",
            "role": "admin",
            "authorized_giveaway_years": [],
            "status": "active",
        }

    def _make_reporter_context(self):
        return {
            "user_id": "user-002",
            "email": "reporter@test.dev",
            "name": "Reporter",
            "role": "reporter",
            "authorized_giveaway_years": ["2025"],
            "status": "active",
        }

    def _make_submitter_context(self):
        return {
            "user_id": "user-003",
            "email": "submitter@test.dev",
            "name": "Submitter",
            "role": "submitter",
            "authorized_giveaway_years": [],
            "status": "active",
        }

    @patch("rbac.authenticate")
    def test_admin_allowed_for_admin_only_endpoint(self, mock_auth):
        mock_auth.return_value = self._make_admin_context()

        @require_role("admin")
        def handler(event, context, user_context):
            return {"statusCode": 200, "body": "ok"}

        resp = handler({"headers": {}}, {})
        assert resp["statusCode"] == 200

    @patch("rbac.authenticate")
    def test_reporter_denied_for_admin_only_endpoint(self, mock_auth):
        mock_auth.return_value = self._make_reporter_context()

        @require_role("admin")
        def handler(event, context, user_context):
            return {"statusCode": 200, "body": "ok"}

        resp = handler({"headers": {}}, {})
        assert resp["statusCode"] == 403
        body = json.loads(resp["body"])
        assert "Forbidden" in body["error"]

    @patch("rbac.authenticate")
    def test_submitter_denied_for_admin_only_endpoint(self, mock_auth):
        mock_auth.return_value = self._make_submitter_context()

        @require_role("admin")
        def handler(event, context, user_context):
            return {"statusCode": 200, "body": "ok"}

        resp = handler({"headers": {}}, {})
        assert resp["statusCode"] == 403

    @patch("rbac.authenticate")
    def test_reporter_allowed_for_multi_role_endpoint(self, mock_auth):
        mock_auth.return_value = self._make_reporter_context()

        @require_role("admin", "reporter")
        def handler(event, context, user_context):
            return {"statusCode": 200, "body": "ok"}

        resp = handler({"headers": {}}, {})
        assert resp["statusCode"] == 200

    @patch("rbac.authenticate")
    def test_user_context_passed_to_handler(self, mock_auth):
        admin_ctx = self._make_admin_context()
        mock_auth.return_value = admin_ctx

        received = {}

        @require_role("admin")
        def handler(event, context, user_context):
            received.update(user_context)
            return {"statusCode": 200}

        handler({"headers": {}}, {})
        assert received["user_id"] == "user-001"
        assert received["role"] == "admin"

    @patch("rbac.authenticate")
    def test_auth_failure_returns_401(self, mock_auth):
        mock_auth.side_effect = AuthError("Missing Authorization header", 401)

        @require_role("admin")
        def handler(event, context, user_context):
            return {"statusCode": 200}

        resp = handler({"headers": {}}, {})
        assert resp["statusCode"] == 401
        body = json.loads(resp["body"])
        assert "Missing Authorization header" in body["error"]

    @patch("rbac.authenticate")
    def test_inactive_user_returns_403(self, mock_auth):
        mock_auth.side_effect = AuthError("User account is inactive", 403)

        @require_role("admin")
        def handler(event, context, user_context):
            return {"statusCode": 200}

        resp = handler({"headers": {}}, {})
        assert resp["statusCode"] == 403

    @patch("rbac.authenticate")
    def test_403_response_has_cors_headers(self, mock_auth):
        mock_auth.return_value = self._make_submitter_context()

        @require_role("admin")
        def handler(event, context, user_context):
            return {"statusCode": 200}

        resp = handler({"headers": {}}, {})
        assert "Access-Control-Allow-Origin" in resp["headers"]

    @patch("rbac.authenticate")
    def test_decorator_preserves_function_name(self, mock_auth):
        mock_auth.return_value = self._make_admin_context()

        @require_role("admin")
        def my_handler(event, context, user_context):
            return {"statusCode": 200}

        assert my_handler.__name__ == "my_handler"
