"""Unit tests for process_document Lambda handler — Textract OCR + Bedrock.

Tests cover:
- S3 event parsing and key extraction
- Textract form field parsing (KEY_VALUE_SET blocks)
- Language detection (English/Spanish) without manual selection (Req 3.8)
- Circle-one selection extraction (gender, contact method, yes/no) (Req 3.15)
- Referring_Agency_Info field mapping (Req 3.14)
- Multi-page document merging into single record (Req 3.9)
- Extraction failure handling (extraction_failed status)
- DynamoDB storage of intermediate OCR results
- Bedrock interpretation of Textract results (Req 3.3)
- Combined per-field confidence scoring (Req 3.5, 4.1)
- Overall application confidence as minimum of per-field scores (Req 4.2)
- Low-confidence field flagging (Req 3.6)
- Status assignment based on confidence threshold (Req 4.3, 4.4)
- Bedrock failure handling (Req 3.7)

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.14, 3.15,
              4.1, 4.2, 4.3, 4.4
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_s3_event(bucket="bbp-hkbg-documents", key="uploads/2025/APP001/page1.pdf"):
    """Build a minimal S3 event notification."""
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


def _make_textract_blocks(key_value_pairs=None, lines=None, selections=None):
    """Build Textract-style Block list from simplified inputs.

    Args:
        key_value_pairs: list of (label, value, confidence) tuples.
        lines: list of text line strings.
        selections: list of (status, confidence) tuples.

    Returns:
        list[dict]: Textract Block dicts.
    """
    blocks = []
    block_id = 0

    for label, value, confidence in (key_value_pairs or []):
        # WORD block for key text
        key_word_id = f"word-key-{block_id}"
        blocks.append({
            "Id": key_word_id,
            "BlockType": "WORD",
            "Text": label,
        })

        # WORD block for value text
        val_word_id = f"word-val-{block_id}"
        blocks.append({
            "Id": val_word_id,
            "BlockType": "WORD",
            "Text": value,
        })

        # VALUE block
        val_block_id = f"val-{block_id}"
        blocks.append({
            "Id": val_block_id,
            "BlockType": "KEY_VALUE_SET",
            "EntityTypes": ["VALUE"],
            "Confidence": confidence,
            "Relationships": [{"Type": "CHILD", "Ids": [val_word_id]}],
        })

        # KEY block
        key_block_id = f"key-{block_id}"
        blocks.append({
            "Id": key_block_id,
            "BlockType": "KEY_VALUE_SET",
            "EntityTypes": ["KEY"],
            "Confidence": confidence,
            "Relationships": [
                {"Type": "CHILD", "Ids": [key_word_id]},
                {"Type": "VALUE", "Ids": [val_block_id]},
            ],
        })

        block_id += 1

    for text in (lines or []):
        blocks.append({
            "Id": f"line-{block_id}",
            "BlockType": "LINE",
            "Text": text,
        })
        block_id += 1

    for status, conf in (selections or []):
        blocks.append({
            "Id": f"sel-{block_id}",
            "BlockType": "SELECTION_ELEMENT",
            "SelectionStatus": status,
            "Confidence": conf,
            "Geometry": {},
        })
        block_id += 1

    return blocks


# ---------------------------------------------------------------------------
# Tests: Textract form field parsing
# ---------------------------------------------------------------------------

class TestParseTextractForms:
    """Tests for parse_textract_forms — extracting key-value pairs."""

    def test_extracts_single_field(self):
        from handler import parse_textract_forms

        blocks = _make_textract_blocks(
            key_value_pairs=[("Agency Name", "Test Agency", 95.0)]
        )
        fields = parse_textract_forms(blocks)
        assert len(fields) == 1
        assert fields[0]["label"] == "Agency Name"
        assert fields[0]["value"] == "Test Agency"
        assert fields[0]["confidence"] == pytest.approx(0.95, abs=0.01)

    def test_extracts_multiple_fields(self):
        from handler import parse_textract_forms

        blocks = _make_textract_blocks(
            key_value_pairs=[
                ("First Name", "Maria", 92.0),
                ("Last Name", "Garcia", 88.0),
                ("Phone", "208-555-0101", 75.0),
            ]
        )
        fields = parse_textract_forms(blocks)
        assert len(fields) == 3
        labels = {f["label"] for f in fields}
        assert labels == {"First Name", "Last Name", "Phone"}

    def test_confidence_normalized_to_0_1(self):
        from handler import parse_textract_forms

        blocks = _make_textract_blocks(
            key_value_pairs=[("City", "Boise", 80.0)]
        )
        fields = parse_textract_forms(blocks)
        assert 0.0 <= fields[0]["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Tests: Language detection (Req 3.8)
# ---------------------------------------------------------------------------

class TestLanguageDetection:
    """Tests for automatic language detection without manual selection."""

    def test_english_text_detected(self):
        from handler import detect_language

        lines = [
            "First Name: John",
            "Last Name: Smith",
            "Address: 123 Main Street",
            "City: Boise",
            "Phone: 208-555-0100",
        ]
        assert detect_language(lines) == "en"

    def test_spanish_text_detected(self):
        from handler import detect_language

        lines = [
            "Nombre de la agencia de referencia",
            "Nombre de contacto teléfono correo electrónico",
            "Dirección ciudad código postal",
            "Idioma principal método de contacto preferido",
            "Altura edad género bicicleta color",
        ]
        assert detect_language(lines) == "es"

    def test_empty_input_defaults_to_english(self):
        from handler import detect_language

        assert detect_language([]) == "en"
        assert detect_language(["", ""]) == "en"


# ---------------------------------------------------------------------------
# Tests: Circle-one selection extraction (Req 3.15)
# ---------------------------------------------------------------------------

class TestCircleOneExtraction:
    """Tests for detecting circled/marked options in form fields."""

    def test_gender_male_resolved(self):
        from handler import _resolve_circle_one

        assert _resolve_circle_one("gender", "Male") == "Male"
        assert _resolve_circle_one("gender", "male") == "Male"
        assert _resolve_circle_one("gender", "M") == "Male"

    def test_gender_female_resolved(self):
        from handler import _resolve_circle_one

        assert _resolve_circle_one("gender", "Female") == "Female"
        assert _resolve_circle_one("gender", "f") == "Female"
        assert _resolve_circle_one("gender", "femenino") == "Female"

    def test_gender_nonbinary_resolved(self):
        from handler import _resolve_circle_one

        assert _resolve_circle_one("gender", "Non-binary") == "Non-binary"
        assert _resolve_circle_one("gender", "non binary") == "Non-binary"

    def test_preferred_contact_method_resolved(self):
        from handler import _resolve_circle_one

        assert _resolve_circle_one("preferred_contact_method", "WhatsApp") == "WhatsApp"
        assert _resolve_circle_one("preferred_contact_method", "phone call") == "Phone Call"
        assert _resolve_circle_one("preferred_contact_method", "text message") == "Text Message"
        assert _resolve_circle_one("preferred_contact_method", "email") == "Email"

    def test_yes_no_fields_resolved(self):
        from handler import _resolve_circle_one

        assert _resolve_circle_one("english_speaker_in_household", "yes") is True
        assert _resolve_circle_one("english_speaker_in_household", "no") is False
        assert _resolve_circle_one("transportation_access", "sí") is True
        assert _resolve_circle_one("knows_how_to_ride", "no") is False

    def test_unknown_circle_key_returns_none(self):
        from handler import _resolve_circle_one

        assert _resolve_circle_one("unknown_field", "yes") is None

    def test_circle_one_in_form_field_mapping(self):
        from handler import map_form_fields_to_record

        fields = [
            {"label": "Gender", "value": "Female", "confidence": 0.85, "block_type": "FORM"},
            {"label": "Preferred Contact Method", "value": "WhatsApp", "confidence": 0.90, "block_type": "FORM"},
            {"label": "English Speaker in Household", "value": "Yes", "confidence": 0.88, "block_type": "FORM"},
            {"label": "Knows How to Ride", "value": "No", "confidence": 0.92, "block_type": "FORM"},
        ]
        result = map_form_fields_to_record(fields)
        assert result["parent_guardian"]["preferred_contact_method"] == "WhatsApp"
        assert result["parent_guardian"]["english_speaker_in_household"] is True
        assert result["children"][0]["gender"] == "Female"
        assert result["children"][0]["knows_how_to_ride"] is False


# ---------------------------------------------------------------------------
# Tests: Referring Agency Info extraction (Req 3.14)
# ---------------------------------------------------------------------------

class TestReferringAgencyExtraction:
    """Tests for extracting Referring_Agency_Info fields."""

    def test_agency_fields_mapped(self):
        from handler import map_form_fields_to_record

        fields = [
            {"label": "Agency Name", "value": "Partner Org", "confidence": 0.95, "block_type": "FORM"},
            {"label": "Contact Name", "value": "Jane Doe", "confidence": 0.88, "block_type": "FORM"},
            {"label": "Contact Phone", "value": "208-555-0100", "confidence": 0.72, "block_type": "FORM"},
            {"label": "Contact Email", "value": "jane@partner.org", "confidence": 0.91, "block_type": "FORM"},
        ]
        result = map_form_fields_to_record(fields)
        agency = result["referring_agency"]
        assert agency["agency_name"] == "Partner Org"
        assert agency["contact_name"] == "Jane Doe"
        assert agency["contact_phone"] == "208-555-0100"
        assert agency["contact_email"] == "jane@partner.org"

    def test_spanish_agency_labels_mapped(self):
        from handler import map_form_fields_to_record

        fields = [
            {"label": "Nombre de la Agencia", "value": "Agencia Comunitaria", "confidence": 0.90, "block_type": "FORM"},
            {"label": "Nombre de Contacto", "value": "Juan Pérez", "confidence": 0.85, "block_type": "FORM"},
        ]
        result = map_form_fields_to_record(fields)
        agency = result["referring_agency"]
        assert agency["agency_name"] == "Agencia Comunitaria"
        assert agency["contact_name"] == "Juan Pérez"

    def test_agency_confidence_stored(self):
        from handler import map_form_fields_to_record

        fields = [
            {"label": "Agency Name", "value": "Test Org", "confidence": 0.93, "block_type": "FORM"},
        ]
        result = map_form_fields_to_record(fields)
        fc = result["field_confidence"]
        assert "referring_agency.agency_name" in fc
        assert fc["referring_agency.agency_name"] == pytest.approx(0.93)


# ---------------------------------------------------------------------------
# Tests: Multi-page document merging (Req 3.9)
# ---------------------------------------------------------------------------

class TestMultiPageMerging:
    """Tests for combining extracted data from multiple pages."""

    def test_agency_fields_merged_across_pages(self):
        from handler import merge_page_results

        page1 = {
            "referring_agency": {"agency_name": "Org A", "contact_name": "Jane"},
            "parent_guardian": {},
            "children": [],
            "field_confidence": {"referring_agency.agency_name": 0.9},
        }
        page2 = {
            "referring_agency": {"contact_phone": "208-555-0100"},
            "parent_guardian": {},
            "children": [],
            "field_confidence": {"referring_agency.contact_phone": 0.8},
        }
        merged = merge_page_results([page1, page2])
        assert merged["referring_agency"]["agency_name"] == "Org A"
        assert merged["referring_agency"]["contact_phone"] == "208-555-0100"

    def test_parent_fields_merged_across_pages(self):
        from handler import merge_page_results

        page1 = {
            "referring_agency": {},
            "parent_guardian": {"first_name": "Maria"},
            "children": [],
            "field_confidence": {"parent_guardian.first_name": 0.92},
        }
        page2 = {
            "referring_agency": {},
            "parent_guardian": {"last_name": "Garcia", "phone": "208-555-0101"},
            "children": [],
            "field_confidence": {
                "parent_guardian.last_name": 0.85,
                "parent_guardian.phone": 0.78,
            },
        }
        merged = merge_page_results([page1, page2])
        assert merged["parent_guardian"]["first_name"] == "Maria"
        assert merged["parent_guardian"]["last_name"] == "Garcia"

    def test_children_accumulated_across_pages(self):
        from handler import merge_page_results

        page1 = {
            "referring_agency": {},
            "parent_guardian": {},
            "children": [{"first_name": "Carlos", "height_inches": 48}],
            "field_confidence": {},
        }
        page2 = {
            "referring_agency": {},
            "parent_guardian": {},
            "children": [{"first_name": "Sofia", "height_inches": 42}],
            "field_confidence": {},
        }
        merged = merge_page_results([page1, page2])
        assert len(merged["children"]) == 2
        assert merged["children"][0]["first_name"] == "Carlos"
        assert merged["children"][1]["first_name"] == "Sofia"

    def test_confidence_scores_merged(self):
        from handler import merge_page_results

        page1 = {
            "referring_agency": {},
            "parent_guardian": {},
            "children": [],
            "field_confidence": {"parent_guardian.first_name": 0.92},
        }
        page2 = {
            "referring_agency": {},
            "parent_guardian": {},
            "children": [],
            "field_confidence": {"parent_guardian.last_name": 0.85},
        }
        merged = merge_page_results([page1, page2])
        fc = merged["field_confidence"]
        assert "parent_guardian.first_name" in fc
        assert "parent_guardian.last_name" in fc


# ---------------------------------------------------------------------------
# Tests: Field mapping
# ---------------------------------------------------------------------------

class TestFieldMapping:
    """Tests for mapping form fields to structured record."""

    def test_parent_guardian_fields_mapped(self):
        from handler import map_form_fields_to_record

        fields = [
            {"label": "First Name", "value": "Maria", "confidence": 0.93, "block_type": "FORM"},
            {"label": "Last Name", "value": "Garcia", "confidence": 0.85, "block_type": "FORM"},
            {"label": "City", "value": "Boise", "confidence": 0.95, "block_type": "FORM"},
        ]
        result = map_form_fields_to_record(fields)
        parent = result["parent_guardian"]
        assert parent["first_name"] == "Maria"
        assert parent["last_name"] == "Garcia"
        assert parent["city"] == "Boise"

    def test_child_fields_mapped(self):
        from handler import map_form_fields_to_record

        fields = [
            {"label": "Child First Name", "value": "Carlos", "confidence": 0.90, "block_type": "FORM"},
            {"label": "Height in Inches", "value": "48", "confidence": 0.78, "block_type": "FORM"},
            {"label": "Age", "value": "8", "confidence": 0.88, "block_type": "FORM"},
        ]
        result = map_form_fields_to_record(fields)
        assert len(result["children"]) == 1
        child = result["children"][0]
        assert child["first_name"] == "Carlos"
        assert child["height_inches"] == 48.0
        assert child["age"] == 8

    def test_empty_value_skipped(self):
        from handler import map_form_fields_to_record

        fields = [
            {"label": "First Name", "value": "", "confidence": 0.90, "block_type": "FORM"},
            {"label": "Last Name", "value": "Garcia", "confidence": 0.85, "block_type": "FORM"},
        ]
        result = map_form_fields_to_record(fields)
        assert "first_name" not in result["parent_guardian"]
        assert result["parent_guardian"]["last_name"] == "Garcia"


# ---------------------------------------------------------------------------
# Tests: S3 event parsing and upload prefix extraction
# ---------------------------------------------------------------------------

class TestS3EventParsing:
    """Tests for S3 event parsing and key extraction."""

    def test_extract_upload_prefix(self):
        from handler import _extract_upload_prefix

        prefix = _extract_upload_prefix("uploads/2025/APP001/page1.pdf")
        assert prefix == "uploads/2025/APP001/"

    def test_extract_upload_prefix_no_match(self):
        from handler import _extract_upload_prefix

        assert _extract_upload_prefix("other/path.pdf") is None

    def test_extract_upload_prefix_short_path(self):
        from handler import _extract_upload_prefix

        assert _extract_upload_prefix("uploads/file.pdf") is None


# ---------------------------------------------------------------------------
# Tests: Handler integration (with mocked Textract + DynamoDB)
# ---------------------------------------------------------------------------

class TestHandlerIntegration:
    """Integration tests for the full handler with mocked AWS services."""

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_reference_number", return_value="2025-0001")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    @patch("handler._get_related_keys", return_value=["uploads/2025/APP001/page1.pdf"])
    @patch("handler.call_textract_analyze")
    @patch("handler._invoke_bedrock")
    @patch("handler._get_confidence_threshold", return_value=0.80)
    def test_successful_single_page_processing(
        self, mock_threshold, mock_bedrock, mock_textract, mock_keys,
        mock_year, mock_ref, mock_table, mock_audit
    ):
        from handler import handler

        mock_textract.return_value = {
            "Blocks": _make_textract_blocks(
                key_value_pairs=[
                    ("Agency Name", "Test Agency", 95.0),
                    ("Contact Name", "Jane Doe", 88.0),
                    ("First Name", "Maria", 92.0),
                    ("Last Name", "Garcia", 85.0),
                ],
                lines=["Agency Name: Test Agency", "First Name: Maria"],
            )
        }
        mock_bedrock.return_value = json.dumps([
            {"label": "Agency Name", "interpreted_value": "Test Agency", "bedrock_confidence": 0.97},
            {"label": "Contact Name", "interpreted_value": "Jane Doe", "bedrock_confidence": 0.95},
            {"label": "First Name", "interpreted_value": "Maria", "bedrock_confidence": 0.96},
            {"label": "Last Name", "interpreted_value": "Garcia", "bedrock_confidence": 0.93},
        ])
        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl

        event = _make_s3_event()
        resp = handler(event, None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["processing_stage"] == "bedrock_complete"
        assert body["pages_processed"] == 1
        assert body["detected_language"] == "en"

        # Verify DynamoDB put_item was called
        mock_tbl.put_item.assert_called_once()
        item = mock_tbl.put_item.call_args[1]["Item"]
        assert item["source_type"] == "upload"
        assert item["giveaway_year"] == "2025"
        assert item["processing_stage"] == "bedrock_complete"
        assert item["reference_number"] == "2025-0001"

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_reference_number", return_value="2025-0001")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    @patch("handler._get_related_keys", return_value=[
        "uploads/2025/APP001/page1.pdf",
        "uploads/2025/APP001/page2.pdf",
    ])
    @patch("handler.call_textract_analyze")
    @patch("handler._invoke_bedrock")
    @patch("handler._get_confidence_threshold", return_value=0.80)
    def test_multi_page_document_combined(
        self, mock_threshold, mock_bedrock, mock_textract, mock_keys,
        mock_year, mock_ref, mock_table, mock_audit
    ):
        """Requirement 3.9: multi-page documents combined into single record."""
        from handler import handler

        # Page 1: agency info
        page1_blocks = _make_textract_blocks(
            key_value_pairs=[
                ("Agency Name", "Partner Org", 95.0),
                ("Contact Name", "Jane Doe", 88.0),
            ],
            lines=["Agency Name: Partner Org"],
        )
        # Page 2: parent info
        page2_blocks = _make_textract_blocks(
            key_value_pairs=[
                ("First Name", "Maria", 92.0),
                ("Last Name", "Garcia", 85.0),
            ],
            lines=["First Name: Maria"],
        )
        mock_textract.side_effect = [
            {"Blocks": page1_blocks},
            {"Blocks": page2_blocks},
        ]
        mock_bedrock.return_value = json.dumps([
            {"label": "Agency Name", "interpreted_value": "Partner Org", "bedrock_confidence": 0.95},
            {"label": "Contact Name", "interpreted_value": "Jane Doe", "bedrock_confidence": 0.92},
            {"label": "First Name", "interpreted_value": "Maria", "bedrock_confidence": 0.94},
            {"label": "Last Name", "interpreted_value": "Garcia", "bedrock_confidence": 0.90},
        ])
        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl

        event = _make_s3_event()
        resp = handler(event, None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["pages_processed"] == 2

        item = mock_tbl.put_item.call_args[1]["Item"]
        assert item["referring_agency"]["agency_name"] == "Partner Org"
        assert item["parent_guardian"]["first_name"] == "Maria"

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    @patch("handler._get_related_keys", return_value=["uploads/2025/APP001/page1.pdf"])
    @patch("handler.call_textract_analyze")
    def test_textract_failure_stores_failed_record(
        self, mock_textract, mock_keys, mock_year, mock_table, mock_audit
    ):
        """Requirement 3.7: extraction failures marked as extraction_failed."""
        from handler import handler

        mock_textract.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterException", "Message": "Bad doc"}},
            "AnalyzeDocument",
        )
        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl

        event = _make_s3_event()
        resp = handler(event, None)

        assert resp["statusCode"] == 500
        # Should have stored a failed record
        mock_tbl.put_item.assert_called_once()
        item = mock_tbl.put_item.call_args[1]["Item"]
        assert item["status"] == "extraction_failed"
        assert item["reference_number"] == ""

    def test_no_records_in_event_returns_400(self):
        from handler import handler

        resp = handler({"Records": []}, None)
        assert resp["statusCode"] == 400

    def test_invalid_event_returns_400(self):
        from handler import handler

        resp = handler({}, None)
        assert resp["statusCode"] == 400

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_reference_number", return_value="2025-0001")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    @patch("handler._get_related_keys", return_value=["uploads/2025/APP001/page1.pdf"])
    @patch("handler.call_textract_analyze")
    @patch("handler._invoke_bedrock")
    @patch("handler._get_confidence_threshold", return_value=0.80)
    def test_spanish_document_detected(
        self, mock_threshold, mock_bedrock, mock_textract, mock_keys,
        mock_year, mock_ref, mock_table, mock_audit
    ):
        """Requirement 3.8: language detected automatically."""
        from handler import handler

        mock_textract.return_value = {
            "Blocks": _make_textract_blocks(
                key_value_pairs=[
                    ("Nombre de la Agencia", "Agencia Comunitaria", 90.0),
                    ("Nombre de Contacto", "Juan Pérez", 85.0),
                ],
                lines=[
                    "Nombre de la agencia de referencia",
                    "Nombre de contacto teléfono correo electrónico",
                    "Dirección ciudad código postal idioma",
                ],
            )
        }
        mock_bedrock.return_value = json.dumps([
            {"label": "Nombre de la Agencia", "interpreted_value": "Agencia Comunitaria", "bedrock_confidence": 0.92},
            {"label": "Nombre de Contacto", "interpreted_value": "Juan Pérez", "bedrock_confidence": 0.88},
        ])
        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl

        event = _make_s3_event()
        resp = handler(event, None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["detected_language"] == "es"

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_reference_number", return_value="2025-0001")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    @patch("handler._get_related_keys", return_value=["uploads/2025/APP001/page1.pdf"])
    @patch("handler.call_textract_analyze")
    @patch("handler._invoke_bedrock")
    @patch("handler._get_confidence_threshold", return_value=0.80)
    def test_audit_log_recorded(
        self, mock_threshold, mock_bedrock, mock_textract, mock_keys,
        mock_year, mock_ref, mock_table, mock_audit
    ):
        from handler import handler

        mock_textract.return_value = {
            "Blocks": _make_textract_blocks(
                key_value_pairs=[("Agency Name", "Test", 90.0)],
                lines=["Agency Name: Test"],
            )
        }
        mock_bedrock.return_value = json.dumps([
            {"label": "Agency Name", "interpreted_value": "Test", "bedrock_confidence": 0.95},
        ])
        mock_table.return_value = MagicMock()

        handler(_make_s3_event(), None)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["action_type"] == "create"
        assert call_kwargs["resource_type"] == "application"
        assert call_kwargs["user_id"] == "system"


# ---------------------------------------------------------------------------
# Tests: Bedrock interpretation stage (Req 3.3, 3.4, 3.5, 3.6, 4.1-4.4)
# ---------------------------------------------------------------------------

class TestCombineConfidence:
    """Tests for _combine_confidence — geometric mean of Textract + Bedrock."""

    def test_both_high_confidence(self):
        from handler import _combine_confidence

        result = _combine_confidence(0.95, 0.97)
        assert result == pytest.approx((0.95 * 0.97) ** 0.5, abs=0.001)
        assert result > 0.9

    def test_one_low_confidence_pulls_down(self):
        from handler import _combine_confidence

        result = _combine_confidence(0.95, 0.40)
        assert result < 0.70

    def test_both_zero(self):
        from handler import _combine_confidence

        assert _combine_confidence(0.0, 0.0) == 0.0

    def test_perfect_scores(self):
        from handler import _combine_confidence

        assert _combine_confidence(1.0, 1.0) == 1.0

    def test_clamps_to_valid_range(self):
        from handler import _combine_confidence

        result = _combine_confidence(1.5, -0.2)
        assert 0.0 <= result <= 1.0


class TestParsBedrockResponse:
    """Tests for _parse_bedrock_response — extracting JSON from model output."""

    def test_valid_json_array(self):
        from handler import _parse_bedrock_response

        text = json.dumps([
            {"label": "First Name", "interpreted_value": "Maria", "bedrock_confidence": 0.95},
        ])
        result = _parse_bedrock_response(text)
        assert len(result) == 1
        assert result[0]["label"] == "First Name"

    def test_json_with_surrounding_text(self):
        from handler import _parse_bedrock_response

        text = 'Here is the result:\n[{"label": "City", "interpreted_value": "Boise", "bedrock_confidence": 0.9}]\nDone.'
        result = _parse_bedrock_response(text)
        assert len(result) == 1
        assert result[0]["interpreted_value"] == "Boise"

    def test_empty_response(self):
        from handler import _parse_bedrock_response

        assert _parse_bedrock_response("") == []
        assert _parse_bedrock_response(None) == []

    def test_invalid_json(self):
        from handler import _parse_bedrock_response

        assert _parse_bedrock_response("not json at all") == []

    def test_no_array_brackets(self):
        from handler import _parse_bedrock_response

        assert _parse_bedrock_response('{"key": "value"}') == []


class TestBuildBedrockPrompt:
    """Tests for _build_bedrock_prompt — prompt construction."""

    def test_includes_field_data(self):
        from handler import _build_bedrock_prompt

        fields = [
            {"label": "First Name", "value": "M4ria", "confidence": 0.72},
        ]
        prompt = _build_bedrock_prompt(fields, "en")
        assert "M4ria" in prompt
        assert "First Name" in prompt
        assert "0.72" in prompt

    def test_spanish_language_note(self):
        from handler import _build_bedrock_prompt

        prompt = _build_bedrock_prompt([], "es")
        assert "Spanish" in prompt

    def test_english_language_note(self):
        from handler import _build_bedrock_prompt

        prompt = _build_bedrock_prompt([], "en")
        assert "English" in prompt

    def test_skips_empty_fields(self):
        from handler import _build_bedrock_prompt

        fields = [
            {"label": "", "value": "test", "confidence": 0.9},
            {"label": "Name", "value": "", "confidence": 0.9},
            {"label": "City", "value": "Boise", "confidence": 0.85},
        ]
        prompt = _build_bedrock_prompt(fields, "en")
        assert "City" in prompt
        assert "Boise" in prompt


class TestRunBedrockInterpretation:
    """Tests for run_bedrock_interpretation — full Bedrock stage logic."""

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_high_confidence_needs_review(self, mock_bedrock, mock_threshold):
        """Req 4.4: overall confidence >= threshold → needs_review."""
        from handler import run_bedrock_interpretation

        mock_bedrock.return_value = json.dumps([
            {"label": "Agency Name", "interpreted_value": "Test Org", "bedrock_confidence": 0.95},
            {"label": "First Name", "interpreted_value": "Maria", "bedrock_confidence": 0.92},
        ])

        record = {
            "textract_raw": [
                {"label": "Agency Name", "value": "Test Org", "confidence": 0.95},
                {"label": "First Name", "value": "Maria", "confidence": 0.92},
            ],
            "detected_language": "en",
            "field_confidence": {
                "referring_agency.agency_name": 0.95,
                "parent_guardian.first_name": 0.92,
            },
            "referring_agency": {"agency_name": "Test Org"},
            "parent_guardian": {"first_name": "Maria"},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        assert result["status"] == "needs_review"
        assert result["processing_stage"] == "bedrock_complete"
        assert result["overall_confidence_score"] >= 0.80

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_low_confidence_needs_review(self, mock_bedrock, mock_threshold):
        """Req 4.3: overall confidence < threshold → needs_review."""
        from handler import run_bedrock_interpretation

        mock_bedrock.return_value = json.dumps([
            {"label": "Agency Name", "interpreted_value": "Test Org", "bedrock_confidence": 0.90},
            {"label": "First Name", "interpreted_value": "M?ria", "bedrock_confidence": 0.40},
        ])

        record = {
            "textract_raw": [
                {"label": "Agency Name", "value": "Test Org", "confidence": 0.95},
                {"label": "First Name", "value": "M4ria", "confidence": 0.50},
            ],
            "detected_language": "en",
            "field_confidence": {
                "referring_agency.agency_name": 0.95,
                "parent_guardian.first_name": 0.50,
            },
            "referring_agency": {"agency_name": "Test Org"},
            "parent_guardian": {"first_name": "M4ria"},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        assert result["status"] == "needs_review"
        assert result["overall_confidence_score"] < 0.80

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_overall_confidence_is_minimum(self, mock_bedrock, mock_threshold):
        """Req 4.2: overall confidence = minimum of all per-field scores."""
        from handler import run_bedrock_interpretation

        mock_bedrock.return_value = json.dumps([
            {"label": "Agency Name", "interpreted_value": "Org", "bedrock_confidence": 0.95},
            {"label": "First Name", "interpreted_value": "Maria", "bedrock_confidence": 0.60},
            {"label": "Last Name", "interpreted_value": "Garcia", "bedrock_confidence": 0.90},
        ])

        record = {
            "textract_raw": [
                {"label": "Agency Name", "value": "Org", "confidence": 0.95},
                {"label": "First Name", "value": "Maria", "confidence": 0.70},
                {"label": "Last Name", "value": "Garcia", "confidence": 0.90},
            ],
            "detected_language": "en",
            "field_confidence": {
                "referring_agency.agency_name": 0.95,
                "parent_guardian.first_name": 0.70,
                "parent_guardian.last_name": 0.90,
            },
            "referring_agency": {"agency_name": "Org"},
            "parent_guardian": {"first_name": "Maria", "last_name": "Garcia"},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        # The minimum combined score should be for first_name
        # Textract=0.70, Bedrock=0.60 → combined = sqrt(0.70*0.60) ≈ 0.6481
        fc = result["field_confidence"]
        min_score = min(fc.values())
        assert result["overall_confidence_score"] == pytest.approx(min_score, abs=0.001)

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_low_confidence_fields_flagged(self, mock_bedrock, mock_threshold):
        """Req 3.6: fields below threshold flagged as low-confidence."""
        from handler import run_bedrock_interpretation

        mock_bedrock.return_value = json.dumps([
            {"label": "Agency Name", "interpreted_value": "Org", "bedrock_confidence": 0.95},
            {"label": "First Name", "interpreted_value": "M?ria", "bedrock_confidence": 0.35},
        ])

        record = {
            "textract_raw": [
                {"label": "Agency Name", "value": "Org", "confidence": 0.95},
                {"label": "First Name", "value": "M4ria", "confidence": 0.45},
            ],
            "detected_language": "en",
            "field_confidence": {
                "referring_agency.agency_name": 0.95,
                "parent_guardian.first_name": 0.45,
            },
            "referring_agency": {"agency_name": "Org"},
            "parent_guardian": {"first_name": "M4ria"},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        assert "low_confidence_fields" in result
        assert len(result["low_confidence_fields"]) > 0
        # first_name should be flagged
        assert any("first_name" in f for f in result["low_confidence_fields"])

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_bedrock_updates_field_values(self, mock_bedrock, mock_threshold):
        """Req 3.3: Bedrock interprets and corrects OCR values."""
        from handler import run_bedrock_interpretation

        mock_bedrock.return_value = json.dumps([
            {"label": "First Name", "interpreted_value": "Maria", "bedrock_confidence": 0.95},
        ])

        record = {
            "textract_raw": [
                {"label": "First Name", "value": "M4ria", "confidence": 0.60},
            ],
            "detected_language": "en",
            "field_confidence": {
                "parent_guardian.first_name": 0.60,
            },
            "referring_agency": {},
            "parent_guardian": {"first_name": "M4ria"},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        # Bedrock should have corrected the value
        assert result["parent_guardian"]["first_name"] == "Maria"

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_empty_textract_raw_skips_bedrock(self, mock_bedrock, mock_threshold):
        """No textract_raw fields → skip Bedrock, still mark bedrock_complete."""
        from handler import run_bedrock_interpretation

        record = {
            "textract_raw": [],
            "detected_language": "en",
            "field_confidence": {},
            "referring_agency": {},
            "parent_guardian": {},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        mock_bedrock.assert_not_called()
        assert result["processing_stage"] == "bedrock_complete"

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_bedrock_stores_raw_response(self, mock_bedrock, mock_threshold):
        """Bedrock raw results stored for debugging."""
        from handler import run_bedrock_interpretation

        bedrock_data = [
            {"label": "City", "interpreted_value": "Boise", "bedrock_confidence": 0.92},
        ]
        mock_bedrock.return_value = json.dumps(bedrock_data)

        record = {
            "textract_raw": [
                {"label": "City", "value": "Boise", "confidence": 0.90},
            ],
            "detected_language": "en",
            "field_confidence": {"parent_guardian.city": 0.90},
            "referring_agency": {},
            "parent_guardian": {"city": "Boise"},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        assert "bedrock_raw" in result
        assert len(result["bedrock_raw"]) == 1

    @patch("handler._get_confidence_threshold", return_value=0.80)
    @patch("handler._invoke_bedrock")
    def test_confidence_threshold_stored_in_record(self, mock_bedrock, mock_threshold):
        """Confidence threshold stored in the application record."""
        from handler import run_bedrock_interpretation

        mock_bedrock.return_value = json.dumps([
            {"label": "City", "interpreted_value": "Boise", "bedrock_confidence": 0.92},
        ])

        record = {
            "textract_raw": [
                {"label": "City", "value": "Boise", "confidence": 0.90},
            ],
            "detected_language": "en",
            "field_confidence": {"parent_guardian.city": 0.90},
            "referring_agency": {},
            "parent_guardian": {"city": "Boise"},
            "children": [],
        }

        result = run_bedrock_interpretation(record)

        assert result["confidence_threshold"] == 0.80


class TestBedrockFailureHandling:
    """Tests for Bedrock failure handling in the handler."""

    @patch("handler.log_audit_event")
    @patch("handler.get_dynamodb_table")
    @patch("handler.generate_reference_number", return_value="2025-0001")
    @patch("handler._get_active_giveaway_year", return_value="2025")
    @patch("handler._get_related_keys", return_value=["uploads/2025/APP001/page1.pdf"])
    @patch("handler.call_textract_analyze")
    @patch("handler._invoke_bedrock")
    @patch("handler._get_confidence_threshold", return_value=0.80)
    def test_bedrock_failure_marks_extraction_failed(
        self, mock_threshold, mock_bedrock, mock_textract, mock_keys,
        mock_year, mock_ref, mock_table, mock_audit
    ):
        """Req 3.7: Bedrock failure → extraction_failed status."""
        from handler import handler

        mock_textract.return_value = {
            "Blocks": _make_textract_blocks(
                key_value_pairs=[("Agency Name", "Test", 90.0)],
                lines=["Agency Name: Test"],
            )
        }
        mock_bedrock.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        mock_tbl = MagicMock()
        mock_table.return_value = mock_tbl

        event = _make_s3_event()
        resp = handler(event, None)

        assert resp["statusCode"] == 200
        mock_tbl.put_item.assert_called_once()
        item = mock_tbl.put_item.call_args[1]["Item"]
        assert item["status"] == "extraction_failed"
        assert item["processing_stage"] == "bedrock_failed"
        assert "error_details" in item


class TestInvokeBedrockUnit:
    """Tests for _invoke_bedrock — Bedrock model invocation."""

    @patch("handler._get_bedrock_client")
    def test_invokes_model_with_correct_params(self, mock_get_client):
        from handler import _invoke_bedrock

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Mock the response
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "content": [{"type": "text", "text": '[{"label":"test"}]'}]
        }).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        result = _invoke_bedrock("test prompt")

        mock_client.invoke_model.assert_called_once()
        call_kwargs = mock_client.invoke_model.call_args[1]
        assert call_kwargs["contentType"] == "application/json"
        assert call_kwargs["accept"] == "application/json"

        # Verify the request body
        body = json.loads(call_kwargs["body"])
        assert body["messages"][0]["content"] == "test prompt"
        assert body["temperature"] == 0.1
        assert result == '[{"label":"test"}]'

    @patch("handler._get_bedrock_client")
    @patch.dict(os.environ, {"BEDROCK_MODEL_ID": "custom-model-id"})
    def test_uses_custom_model_id(self, mock_get_client):
        from handler import _invoke_bedrock

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "content": [{"type": "text", "text": "[]"}]
        }).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        _invoke_bedrock("test")

        call_kwargs = mock_client.invoke_model.call_args[1]
        assert call_kwargs["modelId"] == "custom-model-id"


# ---------------------------------------------------------------------------
# Drawing extraction and analysis tests (Requirements: 3.10-3.13, 10.2, 10.3, 10.7)
# ---------------------------------------------------------------------------


class TestDetectDrawingPageIndex:
    """Tests for _detect_drawing_page_index — drawing page detection."""

    def test_detects_english_drawing_page(self):
        from handler import _detect_drawing_page_index

        page_results = [
            {"raw_text_lines": ["Agency Name: Test", "First Name: Maria"]},
            {"raw_text_lines": ["Draw your dream bike", "My dream bike is..."]},
        ]
        result = _detect_drawing_page_index(page_results)
        assert result == [1]

    def test_detects_spanish_drawing_page(self):
        from handler import _detect_drawing_page_index

        page_results = [
            {"raw_text_lines": ["Nombre de la agencia"]},
            {"raw_text_lines": ["Dibuja tu bicicleta soñada"]},
        ]
        result = _detect_drawing_page_index(page_results)
        assert result == [1]

    def test_no_drawing_page_returns_empty(self):
        from handler import _detect_drawing_page_index

        page_results = [
            {"raw_text_lines": ["Agency Name: Test"]},
            {"raw_text_lines": ["First Name: Maria"]},
        ]
        result = _detect_drawing_page_index(page_results)
        assert result == []

    def test_multiple_drawing_pages(self):
        from handler import _detect_drawing_page_index

        page_results = [
            {"raw_text_lines": ["Agency info"]},
            {"raw_text_lines": ["Dream bike drawing for child 1"]},
            {"raw_text_lines": ["Dream bike drawing for child 2"]},
        ]
        result = _detect_drawing_page_index(page_results)
        assert result == [1, 2]


class TestExtractDreamBikeDescription:
    """Tests for _extract_dream_bike_description — Req 3.13, 10.7."""

    def test_extracts_description_after_prompt(self):
        from handler import _extract_dream_bike_description

        page_results = [
            {"raw_text_lines": [
                "Draw your dream bike",
                "My dream bike is: a blue mountain bike with streamers",
            ]},
        ]
        result = _extract_dream_bike_description(page_results, [0])
        assert "blue mountain bike" in result
        assert "streamers" in result

    def test_extracts_multiline_description(self):
        from handler import _extract_dream_bike_description

        page_results = [
            {"raw_text_lines": [
                "My dream bike is",
                "a red bike",
                "with a basket and bell",
            ]},
        ]
        result = _extract_dream_bike_description(page_results, [0])
        assert "red bike" in result
        assert "basket and bell" in result

    def test_spanish_prompt_extraction(self):
        from handler import _extract_dream_bike_description

        page_results = [
            {"raw_text_lines": [
                "Mi bicicleta soñada es una bicicleta azul",
            ]},
        ]
        result = _extract_dream_bike_description(page_results, [0])
        assert "bicicleta azul" in result

    def test_no_description_returns_empty(self):
        from handler import _extract_dream_bike_description

        page_results = [
            {"raw_text_lines": ["Draw your dream bike", "Some other text"]},
        ]
        result = _extract_dream_bike_description(page_results, [0])
        assert result == ""

    def test_invalid_page_index_handled(self):
        from handler import _extract_dream_bike_description

        page_results = [{"raw_text_lines": ["test"]}]
        result = _extract_dream_bike_description(page_results, [5])
        assert result == ""


class TestParseDrawingKeywords:
    """Tests for _parse_drawing_keywords — Req 3.12."""

    def test_valid_json_array(self):
        from handler import _parse_drawing_keywords

        result = _parse_drawing_keywords('["blue", "mountain bike", "bell"]')
        assert result == ["blue", "mountain bike", "bell"]

    def test_json_with_surrounding_text(self):
        from handler import _parse_drawing_keywords

        result = _parse_drawing_keywords('Here are keywords: ["red", "BMX"]')
        assert result == ["red", "BMX"]

    def test_empty_response(self):
        from handler import _parse_drawing_keywords

        assert _parse_drawing_keywords("") == []
        assert _parse_drawing_keywords(None) == []

    def test_invalid_json(self):
        from handler import _parse_drawing_keywords

        assert _parse_drawing_keywords("not json at all") == []

    def test_filters_empty_strings(self):
        from handler import _parse_drawing_keywords

        result = _parse_drawing_keywords('["blue", "", "red"]')
        assert result == ["blue", "red"]


class TestCropAndStoreDrawing:
    """Tests for _crop_and_store_drawing — Req 3.10, 10.2."""

    @patch("handler._get_s3_client")
    def test_stores_drawing_image_in_s3(self, mock_get_s3):
        from handler import _crop_and_store_drawing

        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        mock_body = MagicMock()
        mock_body.read.return_value = b"\x89PNG fake image data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        result = _crop_and_store_drawing(
            "bbp-hkbg-documents",
            "uploads/2025/APP001/page2.png",
            "APP001", "child-001", "2025",
        )

        assert result == "drawings/2025/APP001/child-001.png"
        mock_s3.put_object.assert_called_once()
        put_kwargs = mock_s3.put_object.call_args[1]
        assert put_kwargs["Bucket"] == "bbp-hkbg-documents"
        assert put_kwargs["Key"] == "drawings/2025/APP001/child-001.png"
        assert put_kwargs["ContentType"] == "image/png"

    @patch("handler._get_s3_client")
    def test_jpeg_content_type(self, mock_get_s3):
        from handler import _crop_and_store_drawing

        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_body = MagicMock()
        mock_body.read.return_value = b"jpeg data"
        mock_s3.get_object.return_value = {"Body": mock_body}

        result = _crop_and_store_drawing(
            "bucket", "uploads/2025/APP001/photo.jpeg",
            "APP001", "child-001", "2025",
        )

        assert result == "drawings/2025/APP001/child-001.png"
        put_kwargs = mock_s3.put_object.call_args[1]
        assert put_kwargs["ContentType"] == "image/jpeg"

    @patch("handler._get_s3_client")
    def test_s3_failure_returns_empty(self, mock_get_s3):
        from handler import _crop_and_store_drawing

        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_s3.get_object.side_effect = Exception("S3 error")

        result = _crop_and_store_drawing(
            "bucket", "uploads/2025/APP001/page.png",
            "APP001", "child-001", "2025",
        )
        assert result == ""


class TestInvokeBedrockWithImage:
    """Tests for _invoke_bedrock_with_image — image analysis invocation."""

    @patch("handler._get_bedrock_client")
    def test_sends_image_and_text(self, mock_get_client):
        from handler import _invoke_bedrock_with_image

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "content": [{"type": "text", "text": '["blue", "BMX"]'}]
        }).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        result = _invoke_bedrock_with_image("Analyze this", b"\x89PNG data")

        mock_client.invoke_model.assert_called_once()
        call_kwargs = mock_client.invoke_model.call_args[1]
        body = json.loads(call_kwargs["body"])
        # Should have image block + text block
        content = body["messages"][0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "image"
        assert content[1]["type"] == "text"
        assert result == '["blue", "BMX"]'

    @patch("handler._get_bedrock_client")
    def test_text_only_when_no_image(self, mock_get_client):
        from handler import _invoke_bedrock_with_image

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({
            "content": [{"type": "text", "text": "[]"}]
        }).encode()
        mock_client.invoke_model.return_value = {"body": mock_body}

        _invoke_bedrock_with_image("Analyze this", None)

        body = json.loads(
            mock_client.invoke_model.call_args[1]["body"]
        )
        content = body["messages"][0]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"


class TestRunDrawingExtraction:
    """Tests for run_drawing_extraction — full drawing pipeline. Req 3.10-3.13."""

    @patch("handler._invoke_bedrock_with_image")
    @patch("handler._get_s3_client")
    def test_extracts_drawing_and_keywords(self, mock_get_s3, mock_bedrock_img):
        from handler import run_drawing_extraction

        # Mock S3 for crop/store and keyword prompt read
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_body = MagicMock()
        mock_body.read.return_value = b"\x89PNG fake"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_bedrock_img.return_value = '["blue", "mountain bike", "streamers"]'

        record = {
            "application_id": "APP001",
            "children": [
                {"child_id": "child-001", "first_name": "Carlos"},
            ],
        }
        page_results = [
            {"raw_text_lines": ["Agency info"]},
            {"raw_text_lines": [
                "Draw your dream bike",
                "My dream bike is a blue mountain bike",
            ]},
        ]
        all_keys = [
            "uploads/2025/APP001/page1.pdf",
            "uploads/2025/APP001/page2.png",
        ]

        result = run_drawing_extraction(
            record, page_results, all_keys, "bbp-hkbg-documents", "2025"
        )

        child = result["children"][0]
        assert child["drawing_image_s3_key"] == "drawings/2025/APP001/child-001.png"
        assert child["drawing_keywords"] == ["blue", "mountain bike", "streamers"]
        assert "blue mountain bike" in child["dream_bike_description"]
        assert result["processing_stage"] == "drawing_complete"

    @patch("handler._invoke_bedrock_with_image")
    @patch("handler._get_s3_client")
    def test_no_drawing_page_skips(self, mock_get_s3, mock_bedrock_img):
        from handler import run_drawing_extraction

        record = {
            "application_id": "APP001",
            "children": [{"child_id": "child-001"}],
        }
        page_results = [
            {"raw_text_lines": ["Agency Name: Test"]},
        ]

        result = run_drawing_extraction(
            record, page_results, ["uploads/2025/APP001/page1.pdf"],
            "bbp-hkbg-documents", "2025",
        )

        # No drawing detected — children unchanged
        assert "drawing_image_s3_key" not in result["children"][0]
        mock_bedrock_img.assert_not_called()


    @patch("handler._invoke_bedrock_with_image")
    @patch("handler._get_s3_client")
    def test_bedrock_failure_sets_empty_keywords(self, mock_get_s3, mock_bedrock_img):
        """Drawing keywords default to empty list on Bedrock failure."""
        from handler import run_drawing_extraction

        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_body = MagicMock()
        mock_body.read.return_value = b"\x89PNG fake"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_bedrock_img.side_effect = Exception("Bedrock error")

        record = {
            "application_id": "APP001",
            "children": [{"child_id": "child-001"}],
        }
        page_results = [
            {"raw_text_lines": ["Dream bike drawing page"]},
        ]

        result = run_drawing_extraction(
            record, page_results, ["uploads/2025/APP001/page1.png"],
            "bbp-hkbg-documents", "2025",
        )

        child = result["children"][0]
        assert child["drawing_keywords"] == []
        # Drawing image should still be stored
        assert child["drawing_image_s3_key"] == "drawings/2025/APP001/child-001.png"

    @patch("handler._invoke_bedrock_with_image")
    @patch("handler._get_s3_client")
    def test_multiple_children_get_drawings(self, mock_get_s3, mock_bedrock_img):
        """Multiple children each get drawing data."""
        from handler import run_drawing_extraction

        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3
        mock_body = MagicMock()
        mock_body.read.return_value = b"\x89PNG fake"
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_bedrock_img.return_value = '["red", "cruiser"]'

        record = {
            "application_id": "APP002",
            "children": [
                {"child_id": "child-001"},
                {"child_id": "child-002"},
            ],
        }
        page_results = [
            {"raw_text_lines": ["Agency info"]},
            {"raw_text_lines": ["Dream bike drawing child 1"]},
            {"raw_text_lines": ["Dream bike drawing child 2"]},
        ]
        all_keys = [
            "uploads/2025/APP002/page1.pdf",
            "uploads/2025/APP002/page2.png",
            "uploads/2025/APP002/page3.png",
        ]

        result = run_drawing_extraction(
            record, page_results, all_keys, "bbp-hkbg-documents", "2025"
        )

        assert result["children"][0]["drawing_image_s3_key"] == \
            "drawings/2025/APP002/child-001.png"
        assert result["children"][1]["drawing_image_s3_key"] == \
            "drawings/2025/APP002/child-002.png"
        assert result["children"][0]["drawing_keywords"] == ["red", "cruiser"]
        assert result["children"][1]["drawing_keywords"] == ["red", "cruiser"]
