"""Process Document Lambda handler — Textract OCR + Bedrock interpretation.

Triggered by S3 event on the uploads prefix. Three-stage pipeline:

Stage 1 (Textract OCR): Calls Textract AnalyzeDocument for OCR and form
field extraction, handles multi-page documents by combining extracted data
from all pages into a single application record, detects language
automatically (English/Spanish), extracts circle-one selections, and
extracts Referring_Agency_Info fields.

Stage 2 (Bedrock interpretation): Passes Textract results to Bedrock for
interpretation of messy handwriting, multilingual content, and ambiguous
values. Computes per-field confidence by combining Textract and Bedrock
scores. Computes overall application confidence as minimum of all per-field
scores. Flags low-confidence fields and sets application status to
"needs_review" based on configurable threshold.

Stage 3 (Drawing extraction): Detects Dream Bike Drawing region in the
uploaded document, crops the drawing area and stores as Drawing_Image in S3,
passes Drawing_Image to Bedrock to generate Drawing_Keywords (colors, bike
style, accessories), extracts "My dream bike is..." handwritten text, and
stores Drawing_Keywords and Dream_Bike_Description in child records.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11,
              3.12, 3.13, 3.14, 3.15, 4.1, 4.2, 4.3, 4.4, 10.2, 10.3, 10.7
"""

import base64
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from audit_middleware import log_audit_event
from utils import generate_application_id, generate_reference_number, get_dynamodb_table

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _floats_to_decimals(obj):
    """Recursively convert float values to Decimal for DynamoDB storage."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimals(i) for i in obj]
    return obj

# AWS clients (module-level for reuse across invocations)
textract_client = None
s3_client = None
bedrock_client = None

# Default Bedrock model and confidence threshold
DEFAULT_BEDROCK_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
DEFAULT_CONFIDENCE_THRESHOLD = 0.80


def _get_textract_client():
    """Return a boto3 Textract client (cached at module level)."""
    global textract_client
    if textract_client is None:
        textract_client = boto3.client("textract")
    return textract_client


def _get_s3_client():
    """Return a boto3 S3 client (cached at module level)."""
    global s3_client
    if s3_client is None:
        s3_client = boto3.client("s3")
    return s3_client


def _get_bedrock_client():
    """Return a boto3 Bedrock Runtime client (cached at module level)."""
    global bedrock_client
    if bedrock_client is None:
        bedrock_client = boto3.client("bedrock-runtime")
    return bedrock_client


# ---------------------------------------------------------------------------
# Field mapping: maps form field labels (English & Spanish) to canonical keys
# ---------------------------------------------------------------------------

# Referring Agency Info field mappings
AGENCY_FIELD_MAP = {
    # English
    "agency name": "agency_name",
    "referring agency": "agency_name",
    "referring agency name": "agency_name",
    "organization": "agency_name",
    "contact name": "contact_name",
    "contact person": "contact_name",
    "contact phone": "contact_phone",
    "phone": "contact_phone",
    "contact email": "contact_email",
    "email": "contact_email",
    # Spanish
    "nombre de la agencia": "agency_name",
    "agencia de referencia": "agency_name",
    "nombre de contacto": "contact_name",
    "persona de contacto": "contact_name",
    "teléfono de contacto": "contact_phone",
    "teléfono": "contact_phone",
    "correo electrónico de contacto": "contact_email",
    "correo electrónico": "contact_email",
    "correo": "contact_email",
}

# Parent/Guardian field mappings
PARENT_FIELD_MAP = {
    # English
    "first name": "first_name",
    "parent first name": "first_name",
    "guardian first name": "first_name",
    "parent/guardian first name": "first_name",
    "last name": "last_name",
    "parent last name": "last_name",
    "guardian last name": "last_name",
    "parent/guardian last name": "last_name",
    "address": "address",
    "street address": "address",
    "city": "city",
    "zip code": "zip_code",
    "zip": "zip_code",
    "phone": "phone",
    "phone number": "phone",
    "email": "email",
    "email address": "email",
    "primary language": "primary_language",
    "primary language spoken": "primary_language",
    "language": "primary_language",
    "preferred contact method": "preferred_contact_method",
    "preferred contact": "preferred_contact_method",
    "contact method": "preferred_contact_method",
    # Spanish
    "nombre": "first_name",
    "primer nombre": "first_name",
    "apellido": "last_name",
    "dirección": "address",
    "ciudad": "city",
    "código postal": "zip_code",
    "teléfono": "phone",
    "número de teléfono": "phone",
    "correo electrónico": "email",
    "idioma principal": "primary_language",
    "idioma": "primary_language",
    "método de contacto preferido": "preferred_contact_method",
}

# Child field mappings
CHILD_FIELD_MAP = {
    # English
    "child first name": "first_name",
    "child's first name": "first_name",
    "child last name": "last_name",
    "child's last name": "last_name",
    "height": "height_inches",
    "height in inches": "height_inches",
    "height (inches)": "height_inches",
    "age": "age",
    "child age": "age",
    "child's age": "age",
    "gender": "gender",
    "bike color 1": "bike_color_1",
    "first color": "bike_color_1",
    "color 1": "bike_color_1",
    "bike color 2": "bike_color_2",
    "second color": "bike_color_2",
    "color 2": "bike_color_2",
    "other siblings enrolled": "other_siblings_enrolled",
    "siblings enrolled": "other_siblings_enrolled",
    "dream bike description": "dream_bike_description",
    "my dream bike is": "dream_bike_description",
    # Spanish
    "nombre del niño": "first_name",
    "nombre del niño/a": "first_name",
    "apellido del niño": "last_name",
    "apellido del niño/a": "last_name",
    "altura": "height_inches",
    "altura en pulgadas": "height_inches",
    "edad": "age",
    "género": "gender",
    "sexo": "gender",
    "color de bicicleta 1": "bike_color_1",
    "color de bicicleta 2": "bike_color_2",
    "otros hermanos inscritos": "other_siblings_enrolled",
    "mi bicicleta soñada es": "dream_bike_description",
}

# Circle-one / selection fields and their valid options
CIRCLE_ONE_FIELDS = {
    "gender": {
        "canonical_key": "gender",
        "section": "child",
        "options": {
            "male": "Male", "female": "Female", "non-binary": "Non-binary",
            "non binary": "Non-binary", "nb": "Non-binary",
            "masculino": "Male", "femenino": "Female", "no binario": "Non-binary",
            "m": "Male", "f": "Female",
        },
    },
    "preferred_contact_method": {
        "canonical_key": "preferred_contact_method",
        "section": "parent",
        "options": {
            "whatsapp": "WhatsApp", "phone call": "Phone Call",
            "phone": "Phone Call", "text message": "Text Message",
            "text": "Text Message", "email": "Email",
            "llamada telefónica": "Phone Call", "llamada": "Phone Call",
            "mensaje de texto": "Text Message", "correo electrónico": "Email",
        },
    },
    "english_speaker_in_household": {
        "canonical_key": "english_speaker_in_household",
        "section": "parent",
        "options": {
            "yes": True, "no": False, "sí": True, "si": True,
            "y": True, "n": False,
        },
    },
    "transportation_access": {
        "canonical_key": "transportation_access",
        "section": "parent",
        "options": {
            "yes": True, "no": False, "sí": True, "si": True,
            "y": True, "n": False,
        },
    },
    "knows_how_to_ride": {
        "canonical_key": "knows_how_to_ride",
        "section": "child",
        "options": {
            "yes": True, "no": False, "sí": True, "si": True,
            "y": True, "n": False,
        },
    },
}

# Labels that indicate circle-one fields (English & Spanish)
CIRCLE_ONE_LABEL_MAP = {
    "gender": "gender",
    "sex": "gender",
    "género": "gender",
    "sexo": "gender",
    "preferred contact method": "preferred_contact_method",
    "preferred contact": "preferred_contact_method",
    "contact method": "preferred_contact_method",
    "método de contacto preferido": "preferred_contact_method",
    "english speaker in household": "english_speaker_in_household",
    "english speaker": "english_speaker_in_household",
    "habla inglés en el hogar": "english_speaker_in_household",
    "transportation access": "transportation_access",
    "transportation access to giveaway event": "transportation_access",
    "acceso a transporte": "transportation_access",
    "knows how to ride": "knows_how_to_ride",
    "knows how to ride a bike": "knows_how_to_ride",
    "sabe andar en bicicleta": "knows_how_to_ride",
}

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

# Common Spanish words used for automatic language detection
SPANISH_INDICATORS = frozenset([
    "nombre", "apellido", "dirección", "ciudad", "teléfono", "correo",
    "idioma", "edad", "género", "sexo", "altura", "bicicleta", "color",
    "hermanos", "sí", "agencia", "contacto", "pulgadas", "soñada",
    "niño", "niña", "hogar", "transporte", "método", "preferido",
    "electrónico", "referencia", "inscrito", "inscritos",
])


def detect_language(text_blocks):
    """Detect document language from extracted text blocks.

    Counts Spanish indicator words across all text. If the ratio exceeds
    a threshold, returns 'es'; otherwise 'en'.

    Args:
        text_blocks: List of text strings extracted from the document.

    Returns:
        str: 'en' for English, 'es' for Spanish.
    """
    if not text_blocks:
        return "en"

    all_text = " ".join(text_blocks).lower()
    words = all_text.split()
    if not words:
        return "en"

    spanish_count = sum(1 for w in words if w.strip(".,;:!?()") in SPANISH_INDICATORS)
    ratio = spanish_count / len(words)
    return "es" if ratio > 0.05 else "en"


# ---------------------------------------------------------------------------
# Textract result parsing
# ---------------------------------------------------------------------------

def _normalize_label(label):
    """Normalize a form field label for matching."""
    if not label:
        return ""
    return label.lower().strip().rstrip(":").strip()


def parse_textract_forms(blocks):
    """Parse Textract blocks to extract key-value form fields.

    Textract returns KEY_VALUE_SET blocks with relationships linking
    keys to values. This function resolves those relationships.

    Args:
        blocks: List of Textract Block dicts from AnalyzeDocument response.

    Returns:
        list[dict]: List of dicts with keys: label, value, confidence, block_type.
    """
    block_map = {b["Id"]: b for b in blocks}
    key_blocks = [b for b in blocks if b.get("BlockType") == "KEY_VALUE_SET"
                  and "KEY" in b.get("EntityTypes", [])]

    form_fields = []
    for key_block in key_blocks:
        key_text = _get_text_from_relationships(key_block, block_map, "CHILD")
        value_text = ""
        value_confidence = key_block.get("Confidence", 0)

        # Find the VALUE block linked to this KEY
        for rel in key_block.get("Relationships", []):
            if rel["Type"] == "VALUE":
                for val_id in rel["Ids"]:
                    val_block = block_map.get(val_id)
                    if val_block:
                        value_text = _get_text_from_relationships(
                            val_block, block_map, "CHILD"
                        )
                        value_confidence = min(
                            value_confidence,
                            val_block.get("Confidence", 0),
                        )

        if key_text:
            form_fields.append({
                "label": key_text,
                "value": value_text,
                "confidence": value_confidence / 100.0,  # Textract uses 0-100
                "block_type": "FORM",
            })

    return form_fields


def _get_text_from_relationships(block, block_map, rel_type):
    """Extract text from a block's CHILD relationships (WORD/SELECTION_ELEMENT).

    Args:
        block: A Textract Block dict.
        block_map: Dict mapping block Id to Block.
        rel_type: Relationship type to follow (usually "CHILD").

    Returns:
        str: Concatenated text from child WORD blocks.
    """
    text_parts = []
    for rel in block.get("Relationships", []):
        if rel["Type"] == rel_type:
            for child_id in rel["Ids"]:
                child = block_map.get(child_id)
                if not child:
                    continue
                if child.get("BlockType") == "WORD":
                    text_parts.append(child.get("Text", ""))
                elif child.get("BlockType") == "SELECTION_ELEMENT":
                    status = child.get("SelectionStatus", "NOT_SELECTED")
                    if status == "SELECTED":
                        text_parts.append("SELECTED")
    return " ".join(text_parts)


def parse_textract_lines(blocks):
    """Extract LINE-level text blocks from Textract response.

    Args:
        blocks: List of Textract Block dicts.

    Returns:
        list[str]: List of text lines.
    """
    return [
        b.get("Text", "")
        for b in blocks
        if b.get("BlockType") == "LINE" and b.get("Text")
    ]


def parse_textract_selections(blocks):
    """Extract SELECTION_ELEMENT blocks (checkboxes, radio buttons).

    Args:
        blocks: List of Textract Block dicts.

    Returns:
        list[dict]: List of dicts with keys: id, status, confidence, geometry.
    """
    selections = []
    for b in blocks:
        if b.get("BlockType") == "SELECTION_ELEMENT":
            selections.append({
                "id": b.get("Id"),
                "status": b.get("SelectionStatus", "NOT_SELECTED"),
                "confidence": b.get("Confidence", 0) / 100.0,
                "geometry": b.get("Geometry", {}),
            })
    return selections


# ---------------------------------------------------------------------------
# Field mapping and circle-one extraction
# ---------------------------------------------------------------------------

def map_form_fields_to_record(form_fields):
    """Map extracted form fields to structured application record sections.

    Args:
        form_fields: List of dicts from parse_textract_forms().

    Returns:
        dict with keys: referring_agency, parent_guardian, children (list),
              field_confidence (dict).
    """
    agency = {}
    parent = {}
    child = {}
    field_confidence = {}

    for field in form_fields:
        label = _normalize_label(field["label"])
        value = field["value"].strip() if field["value"] else ""
        confidence = field["confidence"]

        if not label or not value:
            continue

        # Check circle-one fields first
        circle_key = CIRCLE_ONE_LABEL_MAP.get(label)
        if circle_key:
            resolved = _resolve_circle_one(circle_key, value)
            if resolved is not None:
                info = CIRCLE_ONE_FIELDS[circle_key]
                if info["section"] == "parent":
                    parent[info["canonical_key"]] = resolved
                    field_confidence[f"parent_guardian.{info['canonical_key']}"] = confidence
                elif info["section"] == "child":
                    child[info["canonical_key"]] = resolved
                    field_confidence[f"children[0].{info['canonical_key']}"] = confidence
                continue

        # Try agency fields
        canonical = AGENCY_FIELD_MAP.get(label)
        if canonical:
            agency[canonical] = value
            field_confidence[f"referring_agency.{canonical}"] = confidence
            continue

        # Try parent fields
        canonical = PARENT_FIELD_MAP.get(label)
        if canonical:
            parent[canonical] = value
            field_confidence[f"parent_guardian.{canonical}"] = confidence
            continue

        # Try child fields
        canonical = CHILD_FIELD_MAP.get(label)
        if canonical:
            child[canonical] = value
            field_confidence[f"children[0].{canonical}"] = confidence
            continue

    # Convert height_inches to numeric if present
    if "height_inches" in child:
        try:
            child["height_inches"] = float(child["height_inches"])
        except (TypeError, ValueError):
            pass  # Leave as string for Bedrock to interpret

    # Convert age to numeric if present
    if "age" in child:
        try:
            child["age"] = int(child["age"])
        except (TypeError, ValueError):
            pass

    children = [child] if child else []

    return {
        "referring_agency": agency,
        "parent_guardian": parent,
        "children": children,
        "field_confidence": field_confidence,
    }


def _resolve_circle_one(circle_key, raw_value):
    """Resolve a circle-one selection value to its canonical form.

    Handles SELECTED markers from Textract selection elements,
    as well as plain text values.

    Args:
        circle_key: Key into CIRCLE_ONE_FIELDS.
        raw_value: Raw extracted value string.

    Returns:
        Canonical value or None if unresolvable.
    """
    if circle_key not in CIRCLE_ONE_FIELDS:
        return None

    options = CIRCLE_ONE_FIELDS[circle_key]["options"]
    normalized = raw_value.lower().strip()

    # Direct match
    if normalized in options:
        return options[normalized]

    # Check if any option keyword appears in the value
    for key, canonical in options.items():
        if key in normalized:
            return canonical

    return raw_value  # Return raw value if no match found


# ---------------------------------------------------------------------------
# Multi-page document handling
# ---------------------------------------------------------------------------

def merge_page_results(page_results):
    """Combine extracted data from multiple pages into a single record.

    Later pages' fields override earlier pages' fields (last-write-wins)
    for agency and parent sections. Children are accumulated across pages.

    Args:
        page_results: List of dicts from map_form_fields_to_record(),
                      one per page.

    Returns:
        dict: Merged record with referring_agency, parent_guardian,
              children, field_confidence.
    """
    merged_agency = {}
    merged_parent = {}
    merged_children = []
    merged_confidence = {}

    for page in page_results:
        # Merge agency fields (later pages override)
        merged_agency.update(page.get("referring_agency", {}))
        # Merge parent fields (later pages override)
        merged_parent.update(page.get("parent_guardian", {}))
        # Accumulate children
        page_children = page.get("children", [])
        if page_children:
            # If the first page already has a child, merge fields into it
            # if the new page's child looks like the same child (no name yet)
            if merged_children and page_children:
                last_child = merged_children[-1]
                new_child = page_children[0]
                # If the new child has a name, it's a new child entry
                if new_child.get("first_name") and last_child.get("first_name"):
                    merged_children.extend(page_children)
                else:
                    # Merge into existing child
                    last_child.update(new_child)
                    if len(page_children) > 1:
                        merged_children.extend(page_children[1:])
            else:
                merged_children.extend(page_children)
        # Merge confidence scores (later pages override)
        merged_confidence.update(page.get("field_confidence", {}))

    # Re-index children
    for i, child in enumerate(merged_children):
        child["child_id"] = f"child-{i + 1:03d}"
        # Update confidence keys for re-indexed children
        old_prefix = "children[0]."
        new_prefix = f"children[{i}]."
        if i > 0:
            for key in list(merged_confidence.keys()):
                if key.startswith(old_prefix):
                    new_key = key.replace(old_prefix, new_prefix, 1)
                    if new_key not in merged_confidence:
                        merged_confidence[new_key] = merged_confidence[key]

    return {
        "referring_agency": merged_agency,
        "parent_guardian": merged_parent,
        "children": merged_children,
        "field_confidence": merged_confidence,
    }


# ---------------------------------------------------------------------------
# Textract invocation
# ---------------------------------------------------------------------------

def call_textract_analyze(bucket, key):
    """Call Textract AnalyzeDocument for a single document page/file.

    Uses FORMS and TABLES feature types for form field extraction.

    Args:
        bucket: S3 bucket name.
        key: S3 object key.

    Returns:
        dict: Textract AnalyzeDocument response.

    Raises:
        ClientError: If Textract call fails.
    """
    client = _get_textract_client()
    response = client.analyze_document(
        Document={
            "S3Object": {
                "Bucket": bucket,
                "Name": key,
            }
        },
        FeatureTypes=["FORMS"],
    )
    return response


def process_single_page(bucket, key):
    """Process a single page/file through Textract and parse results.

    Args:
        bucket: S3 bucket name.
        key: S3 object key.

    Returns:
        dict: Parsed result with referring_agency, parent_guardian,
              children, field_confidence, raw_text_lines, detected_language.
    """
    response = call_textract_analyze(bucket, key)
    blocks = response.get("Blocks", [])

    # Parse form fields
    form_fields = parse_textract_forms(blocks)

    # Parse text lines for language detection
    text_lines = parse_textract_lines(blocks)

    # Map to structured record
    record = map_form_fields_to_record(form_fields)

    # Detect language
    detected_language = detect_language(text_lines)

    record["raw_text_lines"] = text_lines
    record["detected_language"] = detected_language
    record["raw_form_fields"] = form_fields

    return record


# ---------------------------------------------------------------------------
# S3 event parsing and multi-page support
# ---------------------------------------------------------------------------

def _get_related_keys(bucket, prefix):
    """List all S3 objects under a prefix (for multi-page documents).

    Args:
        bucket: S3 bucket name.
        prefix: S3 key prefix (e.g. uploads/2025/APP_ID/).

    Returns:
        list[str]: Sorted list of S3 keys under the prefix.
    """
    client = _get_s3_client()
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return sorted(keys)


def _extract_upload_prefix(key):
    """Extract the application-level prefix from an upload key.

    Expected key format: uploads/{year}/{app_id}/filename
    Returns: uploads/{year}/{app_id}/

    Args:
        key: S3 object key.

    Returns:
        str or None: The prefix up to and including the app_id directory.
    """
    parts = key.split("/")
    # uploads / year / app_id / filename
    if len(parts) >= 4 and parts[0] == "uploads":
        return "/".join(parts[:3]) + "/"
    return None


def _build_application_record(merged, bucket, key, giveaway_year):
    """Build the DynamoDB application record from merged OCR results.

    Args:
        merged: Merged record from merge_page_results().
        bucket: S3 bucket name.
        key: Original triggering S3 key.
        giveaway_year: Active giveaway year string.

    Returns:
        dict: Application record ready for DynamoDB.
    """
    application_id = generate_application_id()
    reference_number = generate_reference_number(giveaway_year)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # Assign child IDs if not already set
    children = merged.get("children", [])
    for i, child in enumerate(children):
        if "child_id" not in child:
            child["child_id"] = f"child-{i + 1:03d}"

    record = {
        "application_id": application_id,
        "reference_number": reference_number,
        "giveaway_year": giveaway_year,
        "submission_timestamp": timestamp,
        "source_type": "upload",
        "status": "needs_review",
        "overall_confidence_score": 0.0,
        "referring_agency": merged.get("referring_agency", {}),
        "parent_guardian": merged.get("parent_guardian", {}),
        "children": children,
        "field_confidence": merged.get("field_confidence", {}),
        "detected_language": merged.get("detected_language", "en"),
        "original_documents": [{"s3_key": key, "upload_timestamp": timestamp}],
        "textract_raw": merged.get("raw_form_fields", []),
        "version": 1,
        "processing_stage": "textract_complete",
    }

    # Compute overall confidence as minimum of all field scores
    fc = merged.get("field_confidence", {})
    record["field_confidence"] = fc
    if fc:
        record["overall_confidence_score"] = round(min(fc.values()), 4)

    return record, application_id


def _get_active_giveaway_year():
    """Read the active giveaway year from the Config table."""
    config_table = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
    table = get_dynamodb_table(config_table)
    resp = table.get_item(Key={"config_key": "active_giveaway_year"})
    item = resp.get("Item")
    if item and "value" in item:
        return str(item["value"])
    return str(datetime.now(timezone.utc).year)


# ---------------------------------------------------------------------------
# Bedrock interpretation stage (Requirements: 3.3, 3.4, 3.5, 3.6, 4.1-4.4)
# ---------------------------------------------------------------------------

def _get_confidence_threshold():
    """Read the confidence threshold from the Config DynamoDB table.

    Falls back to DEFAULT_CONFIDENCE_THRESHOLD (0.80) if not configured.

    Returns:
        Decimal: Confidence threshold between 0.0 and 1.0.
    """
    try:
        config_table = os.environ.get("CONFIG_TABLE_NAME", "bbp-hkbg-config")
        table = get_dynamodb_table(config_table)
        resp = table.get_item(Key={"config_key": "confidence_threshold"})
        item = resp.get("Item")
        if item and "value" in item:
            return float(item["value"])
    except Exception:
        logger.exception("Failed to read confidence threshold from config")
    return DEFAULT_CONFIDENCE_THRESHOLD


def _build_bedrock_prompt(textract_fields, detected_language):
    """Build a prompt for Bedrock to interpret Textract OCR results.

    Asks the model to correct likely OCR errors in messy handwriting,
    handle multilingual content, resolve ambiguous values, and provide
    a confidence score for each interpretation.

    Args:
        textract_fields: List of dicts with label, value, confidence keys
            from Textract form extraction.
        detected_language: Detected document language ('en' or 'es').

    Returns:
        str: The prompt string for Bedrock.
    """
    fields_text = "\n".join(
        f"  - \"{f['label']}\": \"{f['value']}\" (OCR confidence: {f['confidence']:.2f})"
        for f in textract_fields
        if f.get("label") and f.get("value")
    )

    lang_note = (
        "The document appears to be in Spanish."
        if detected_language == "es"
        else "The document appears to be in English."
    )

    return f"""You are an expert at interpreting OCR results from handwritten forms.
{lang_note}

Below are form fields extracted by OCR from a scanned application form.
Some values may contain errors from messy handwriting, smudges, or multilingual content.

Extracted fields:
{fields_text}

For each field, provide:
1. Your best interpretation of the correct value
2. A confidence score (0.0 to 1.0) for your interpretation

Respond ONLY with a valid JSON array. Each element must have exactly these keys:
- "label": the original field label (string)
- "interpreted_value": your corrected/interpreted value (string)
- "bedrock_confidence": your confidence in the interpretation (number 0.0-1.0)

Example response format:
[
  {{"label": "First Name", "interpreted_value": "Maria", "bedrock_confidence": 0.95}},
  {{"label": "Phone", "interpreted_value": "208-555-0100", "bedrock_confidence": 0.88}}
]

Respond with ONLY the JSON array, no other text."""


def _invoke_bedrock(prompt):
    """Invoke Bedrock model with the given prompt.

    Args:
        prompt: The prompt string.

    Returns:
        str: The model's response text.

    Raises:
        Exception: If the Bedrock invocation fails.
    """
    client = _get_bedrock_client()
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)

    request_body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.1,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    })

    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=request_body,
    )

    response_body = json.loads(response["body"].read())
    # Extract text from Anthropic response format
    content = response_body.get("content", [])
    if content and isinstance(content, list):
        return content[0].get("text", "")
    return ""


def _parse_bedrock_response(response_text):
    """Parse the JSON array from Bedrock's response.

    Args:
        response_text: Raw text response from Bedrock.

    Returns:
        list[dict]: Parsed list of field interpretations, or empty list
            if parsing fails.
    """
    if not response_text:
        return []

    # Try to extract JSON array from the response
    text = response_text.strip()

    # Find the JSON array boundaries
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        logger.warning("No JSON array found in Bedrock response")
        return []

    try:
        parsed = json.loads(text[start:end + 1])
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        logger.warning("Failed to parse Bedrock response as JSON")

    return []


def _combine_confidence(textract_confidence, bedrock_confidence):
    """Combine Textract and Bedrock confidence scores for a field.

    Uses the geometric mean of the two scores, which penalises low
    confidence from either source more than an arithmetic mean would.

    Args:
        textract_confidence: Textract confidence (0.0-1.0).
        bedrock_confidence: Bedrock confidence (0.0-1.0).

    Returns:
        float: Combined confidence score (0.0-1.0), rounded to 4 decimals.
    """
    tc = max(0.0, min(1.0, float(textract_confidence)))
    bc = max(0.0, min(1.0, float(bedrock_confidence)))
    combined = (tc * bc) ** 0.5
    return round(combined, 4)


def run_bedrock_interpretation(record):
    """Run Bedrock interpretation on a Textract-processed application record.

    Takes the textract_raw fields, sends them to Bedrock for interpretation,
    then updates the record with:
    - Bedrock-interpreted field values (where applicable)
    - Combined per-field confidence scores
    - Overall application confidence (minimum of all per-field scores)
    - Low-confidence field flags
    - Application status based on confidence threshold

    Args:
        record: The application record dict (must have textract_raw and
            field_confidence keys).

    Returns:
        dict: Updated record with Bedrock results applied.
    """
    textract_fields = record.get("textract_raw", [])
    detected_language = record.get("detected_language", "en")
    field_confidence = dict(record.get("field_confidence", {}))

    if not textract_fields:
        logger.warning("No textract_raw fields to interpret")
        record["processing_stage"] = "bedrock_complete"
        return record

    # Build prompt and invoke Bedrock
    prompt = _build_bedrock_prompt(textract_fields, detected_language)
    response_text = _invoke_bedrock(prompt)
    bedrock_results = _parse_bedrock_response(response_text)

    # Build lookup from Bedrock results keyed by normalized label
    bedrock_lookup = {}
    for br in bedrock_results:
        label = _normalize_label(br.get("label", ""))
        if label:
            bedrock_lookup[label] = br

    # Store raw Bedrock response for debugging
    record["bedrock_raw"] = bedrock_results

    # Update field values and compute combined confidence scores
    for tf in textract_fields:
        label = _normalize_label(tf.get("label", ""))
        if not label:
            continue

        textract_conf = tf.get("confidence", 0.0)
        br = bedrock_lookup.get(label)

        if br:
            bedrock_conf = br.get("bedrock_confidence", 0.5)
            combined = _combine_confidence(textract_conf, bedrock_conf)
            interpreted_value = br.get("interpreted_value", tf.get("value", ""))

            # Update the corresponding field confidence in the record
            _update_field_confidence_and_value(
                record, label, interpreted_value, combined, field_confidence
            )
        else:
            # No Bedrock result for this field — keep Textract confidence
            # but apply a slight penalty since Bedrock couldn't interpret it
            combined = _combine_confidence(textract_conf, 0.5)
            _update_field_confidence_only(label, combined, field_confidence)

    # Apply updated confidence map
    record["field_confidence"] = field_confidence

    # Compute overall confidence as minimum of all per-field scores
    threshold = _get_confidence_threshold()
    if field_confidence:
        overall = round(min(field_confidence.values()), 4)
    else:
        overall = 0.0
    record["overall_confidence_score"] = overall
    record["confidence_threshold"] = threshold

    # Flag low-confidence fields
    low_confidence_fields = [
        k for k, v in field_confidence.items() if v < threshold
    ]
    record["low_confidence_fields"] = low_confidence_fields

    # Set application status based on threshold
    if overall >= threshold:
        record["status"] = "needs_review"
    else:
        record["status"] = "needs_review"

    record["processing_stage"] = "bedrock_complete"

    return record


def _update_field_confidence_and_value(
    record, label, interpreted_value, combined_confidence, field_confidence
):
    """Update a field's value and confidence in the record.

    Finds the canonical field path for the label and updates both the
    nested value in the record and the field_confidence map.

    Args:
        record: Application record dict.
        label: Normalized form field label.
        interpreted_value: Bedrock-interpreted value.
        combined_confidence: Combined Textract+Bedrock confidence.
        field_confidence: The field_confidence dict to update.
    """
    # Find which confidence key corresponds to this label
    canonical_key = _find_canonical_key(label)
    if not canonical_key:
        return

    # Update confidence
    for fc_key in list(field_confidence.keys()):
        if fc_key.endswith(f".{canonical_key}"):
            field_confidence[fc_key] = combined_confidence
            # Also update the value in the record
            _set_nested_value(record, fc_key, interpreted_value)
            return

    # If no existing key found, try to add it based on section detection
    section = _detect_section(label)
    if section:
        fc_path = f"{section}.{canonical_key}"
        field_confidence[fc_path] = combined_confidence
        _set_nested_value(record, fc_path, interpreted_value)


def _update_field_confidence_only(label, combined_confidence, field_confidence):
    """Update only the confidence score for a field (no value change).

    Args:
        label: Normalized form field label.
        combined_confidence: Combined confidence score.
        field_confidence: The field_confidence dict to update.
    """
    canonical_key = _find_canonical_key(label)
    if not canonical_key:
        return

    for fc_key in list(field_confidence.keys()):
        if fc_key.endswith(f".{canonical_key}"):
            field_confidence[fc_key] = combined_confidence
            return


def _find_canonical_key(label):
    """Find the canonical field key for a normalized label.

    Searches AGENCY_FIELD_MAP, PARENT_FIELD_MAP, CHILD_FIELD_MAP,
    and CIRCLE_ONE_LABEL_MAP.

    Args:
        label: Normalized form field label.

    Returns:
        str or None: Canonical key name.
    """
    # Check circle-one labels
    circle_key = CIRCLE_ONE_LABEL_MAP.get(label)
    if circle_key:
        return CIRCLE_ONE_FIELDS[circle_key]["canonical_key"]

    # Check field maps
    for field_map in (AGENCY_FIELD_MAP, PARENT_FIELD_MAP, CHILD_FIELD_MAP):
        if label in field_map:
            return field_map[label]

    return None


def _detect_section(label):
    """Detect which record section a label belongs to.

    Args:
        label: Normalized form field label.

    Returns:
        str or None: Section path like 'referring_agency', 'parent_guardian',
            or 'children[0]'.
    """
    if label in AGENCY_FIELD_MAP:
        return "referring_agency"
    if label in PARENT_FIELD_MAP:
        return "parent_guardian"
    if label in CHILD_FIELD_MAP:
        return "children[0]"
    circle_key = CIRCLE_ONE_LABEL_MAP.get(label)
    if circle_key:
        info = CIRCLE_ONE_FIELDS[circle_key]
        if info["section"] == "parent":
            return "parent_guardian"
        if info["section"] == "child":
            return "children[0]"
    return None


def _set_nested_value(record, fc_path, value):
    """Set a value in the record based on a field_confidence path.

    Handles paths like 'referring_agency.agency_name',
    'parent_guardian.first_name', 'children[0].first_name'.

    Args:
        record: Application record dict.
        fc_path: Dot-separated path from field_confidence keys.
        value: Value to set.
    """
    import re

    parts = fc_path.split(".")
    if len(parts) < 2:
        return

    section = parts[0]
    field = parts[1]

    # Handle children[N] paths
    match = re.match(r"children\[(\d+)\]", section)
    if match:
        idx = int(match.group(1))
        children = record.get("children", [])
        if idx < len(children):
            children[idx][field] = value
        return

    # Handle top-level sections
    if section in record and isinstance(record[section], dict):
        record[section][field] = value


# ---------------------------------------------------------------------------
# Drawing extraction and analysis (Requirements: 3.10-3.13, 10.2, 10.3, 10.7)
# ---------------------------------------------------------------------------

# Keywords/phrases that indicate a drawing page in OCR text
DRAWING_PAGE_INDICATORS = [
    "dream bike",
    "my dream bike",
    "my dream bike is",
    "draw your dream bike",
    "dream bike drawing",
    "bicicleta soñada",
    "mi bicicleta soñada",
    "dibuja tu bicicleta",
    "drawing",
    "dibujo",
]


def _detect_drawing_page_index(page_results):
    """Detect which page(s) contain the Dream Bike Drawing region.

    Scans raw text lines from each page for drawing-related keywords.

    Args:
        page_results: List of per-page result dicts from process_single_page.

    Returns:
        list[int]: Indices of pages that contain drawing content.
    """
    drawing_pages = []
    for i, page in enumerate(page_results):
        text_lines = page.get("raw_text_lines", [])
        combined_text = " ".join(text_lines).lower()
        for indicator in DRAWING_PAGE_INDICATORS:
            if indicator in combined_text:
                drawing_pages.append(i)
                break
    return drawing_pages


def _extract_dream_bike_description(page_results, drawing_page_indices):
    """Extract the 'My dream bike is...' handwritten text from drawing pages.

    Looks for text lines that follow the 'My dream bike is' prompt on
    the identified drawing pages.

    Requirements: 3.13, 10.7

    Args:
        page_results: List of per-page result dicts.
        drawing_page_indices: Indices of pages with drawing content.

    Returns:
        str: The extracted dream bike description, or empty string.
    """
    description_parts = []

    for idx in drawing_page_indices:
        if idx >= len(page_results):
            continue
        text_lines = page_results[idx].get("raw_text_lines", [])

        capture = False
        for line in text_lines:
            lower = line.lower().strip()
            # Check if this line contains the prompt
            if "my dream bike is" in lower or "mi bicicleta soñada es" in lower:
                # Extract text after the prompt on the same line
                for prompt in ["my dream bike is", "mi bicicleta soñada es"]:
                    pos = lower.find(prompt)
                    if pos != -1:
                        after = line[pos + len(prompt):].strip().lstrip(".:").strip()
                        if after:
                            description_parts.append(after)
                capture = True
                continue
            if capture:
                # Stop capturing at known section boundaries
                if any(kw in lower for kw in [
                    "dream bike drawing", "draw your dream bike",
                    "dibuja tu bicicleta", "page", "signature",
                ]):
                    break
                stripped = line.strip()
                if stripped:
                    description_parts.append(stripped)

    return " ".join(description_parts).strip()


def _crop_and_store_drawing(bucket, page_key, application_id, child_id,
                            giveaway_year):
    """Download the drawing page image from S3, store as Drawing_Image.

    For scanned documents, the entire page is treated as the drawing
    region since precise pixel-level cropping requires image processing
    libraries that may not be available in Lambda. The full page image
    is stored as the Drawing_Image.

    Requirements: 3.10, 10.2

    Args:
        bucket: S3 bucket name.
        page_key: S3 key of the page containing the drawing.
        application_id: Application ID string.
        child_id: Child ID string (e.g. 'child-001').
        giveaway_year: Giveaway year string.

    Returns:
        str: S3 key where the Drawing_Image was stored, or empty string
            on failure.
    """
    s3 = _get_s3_client()
    drawing_s3_key = (
        f"drawings/{giveaway_year}/{application_id}/{child_id}.png"
    )

    try:
        # Download the source page
        response = s3.get_object(Bucket=bucket, Key=page_key)
        image_bytes = response["Body"].read()

        # Store as Drawing_Image
        content_type = "image/png"
        if page_key.lower().endswith(".jpg") or page_key.lower().endswith(".jpeg"):
            content_type = "image/jpeg"
        elif page_key.lower().endswith(".pdf"):
            content_type = "application/pdf"

        s3.put_object(
            Bucket=bucket,
            Key=drawing_s3_key,
            Body=image_bytes,
            ContentType=content_type,
        )
        logger.info("Stored Drawing_Image at s3://%s/%s", bucket, drawing_s3_key)
        return drawing_s3_key

    except Exception:
        logger.exception(
            "Failed to crop/store drawing for %s/%s", application_id, child_id
        )
        return ""


def _build_drawing_keywords_prompt(drawing_s3_key, bucket):
    """Build a Bedrock prompt to analyze a Drawing_Image for keywords.

    Requirements: 3.11, 10.3

    Args:
        drawing_s3_key: S3 key of the Drawing_Image.
        bucket: S3 bucket name.

    Returns:
        tuple: (prompt_text, image_bytes) or (prompt_text, None) if image
            cannot be read.
    """
    s3 = _get_s3_client()
    try:
        response = s3.get_object(Bucket=bucket, Key=drawing_s3_key)
        image_bytes = response["Body"].read()
    except Exception:
        logger.exception("Failed to read drawing image for analysis")
        image_bytes = None

    prompt_text = (
        "You are analyzing a child's hand-drawn picture of their dream bicycle. "
        "Identify and list descriptive keywords for this drawing. Include:\n"
        "- Primary color(s) visible in the drawing\n"
        "- Secondary color(s) if any\n"
        "- Bike style (e.g., mountain, BMX, cruiser, road, tricycle)\n"
        "- Any accessories or features depicted (e.g., basket, streamers, bell, "
        "water bottle, horn, lights, training wheels, flag)\n\n"
        "Respond ONLY with a valid JSON array of keyword strings. "
        "Example: [\"blue\", \"mountain bike\", \"streamers\", \"bell\"]\n"
        "Respond with ONLY the JSON array, no other text."
    )

    return prompt_text, image_bytes


def _invoke_bedrock_with_image(prompt_text, image_bytes):
    """Invoke Bedrock with a text prompt and an image for analysis.

    Uses the Anthropic Messages API with image content blocks.

    Args:
        prompt_text: The text prompt.
        image_bytes: Raw image bytes, or None for text-only.

    Returns:
        str: The model's response text.
    """
    client = _get_bedrock_client()
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)

    content_blocks = []
    if image_bytes:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        # Detect media type from magic bytes
        media_type = "image/png"
        if image_bytes[:2] == b"\xff\xd8":
            media_type = "image/jpeg"
        elif image_bytes[:4] == b"%PDF":
            media_type = "application/pdf"

        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": encoded,
            },
        })

    content_blocks.append({"type": "text", "text": prompt_text})

    request_body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": content_blocks}],
    })

    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=request_body,
    )

    response_body = json.loads(response["body"].read())
    content = response_body.get("content", [])
    if content and isinstance(content, list):
        return content[0].get("text", "")
    return ""


def _parse_drawing_keywords(response_text):
    """Parse Drawing_Keywords from Bedrock's response.

    Expects a JSON array of strings.

    Args:
        response_text: Raw text response from Bedrock.

    Returns:
        list[str]: List of keyword strings, or empty list on failure.
    """
    if not response_text:
        return []

    text = response_text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []

    try:
        parsed = json.loads(text[start:end + 1])
        if isinstance(parsed, list):
            return [str(kw) for kw in parsed if kw]
    except json.JSONDecodeError:
        logger.warning("Failed to parse drawing keywords JSON")

    return []


def run_drawing_extraction(record, page_results, all_keys, bucket,
                           giveaway_year):
    """Run drawing extraction and analysis on the processed document.

    Detects drawing pages, crops and stores Drawing_Image in S3, invokes
    Bedrock to generate Drawing_Keywords, extracts Dream_Bike_Description,
    and updates child records.

    Requirements: 3.10, 3.11, 3.12, 3.13, 10.2, 10.3, 10.7

    Args:
        record: The application record dict (already has children list).
        page_results: List of per-page result dicts from Textract.
        all_keys: List of S3 keys for all pages.
        bucket: S3 bucket name.
        giveaway_year: Giveaway year string.

    Returns:
        dict: Updated record with drawing data in child records.
    """
    application_id = record.get("application_id", "unknown")
    children = record.get("children", [])

    # Detect which pages contain drawing content
    drawing_page_indices = _detect_drawing_page_index(page_results)

    if not drawing_page_indices:
        logger.info("No drawing pages detected for app_id=%s", application_id)
        return record

    logger.info(
        "Drawing pages detected: %s for app_id=%s",
        drawing_page_indices, application_id,
    )

    # Extract dream bike description from drawing pages
    dream_description = _extract_dream_bike_description(
        page_results, drawing_page_indices
    )

    # Process drawing for each child (assign drawing pages round-robin
    # if multiple children, or all to first child if only one)
    for child_idx, child in enumerate(children):
        child_id = child.get("child_id", f"child-{child_idx + 1:03d}")

        # Determine which drawing page to use for this child
        if child_idx < len(drawing_page_indices):
            page_idx = drawing_page_indices[child_idx]
        else:
            # More children than drawing pages — use last drawing page
            page_idx = drawing_page_indices[-1]

        # Get the S3 key for the drawing page
        if page_idx < len(all_keys):
            page_key = all_keys[page_idx]
        else:
            page_key = all_keys[-1] if all_keys else None

        if not page_key:
            continue

        # Crop and store Drawing_Image in S3
        drawing_s3_key = _crop_and_store_drawing(
            bucket, page_key, application_id, child_id, giveaway_year
        )

        if drawing_s3_key:
            child["drawing_image_s3_key"] = drawing_s3_key

            # Analyze drawing with Bedrock for keywords
            try:
                prompt_text, image_bytes = _build_drawing_keywords_prompt(
                    drawing_s3_key, bucket
                )
                response_text = _invoke_bedrock_with_image(
                    prompt_text, image_bytes
                )
                keywords = _parse_drawing_keywords(response_text)
                child["drawing_keywords"] = keywords
                logger.info(
                    "Drawing keywords for %s/%s: %s",
                    application_id, child_id, keywords,
                )
            except Exception:
                logger.exception(
                    "Failed to analyze drawing for %s/%s",
                    application_id, child_id,
                )
                child["drawing_keywords"] = []

        # Store dream bike description
        if dream_description:
            child["dream_bike_description"] = dream_description

    record["children"] = children
    record["processing_stage"] = "drawing_complete"

    return record


def handler(event, context):
    """Process uploaded document: Textract OCR + Bedrock interpretation.

    Triggered by S3 event on uploads prefix. Extracts form fields,
    detects language, resolves circle-one selections, interprets via
    Bedrock, computes confidence scores, and stores final results
    in DynamoDB.

    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9,
                  3.10, 3.11, 3.12, 3.13, 3.14, 3.15,
                  4.1, 4.2, 4.3, 4.4, 10.2, 10.3, 10.7
    """
    logger.info("process_document invoked")

    # Parse S3 event
    try:
        records = event.get("Records", [])
        if not records:
            logger.error("No records in S3 event")
            return {"statusCode": 400, "body": "No S3 records"}

        s3_info = records[0]["s3"]
        bucket = s3_info["bucket"]["name"]
        key = s3_info["object"]["key"]
        # URL-decode the key (S3 events URL-encode special chars)
        import urllib.parse
        key = urllib.parse.unquote_plus(key)
    except (KeyError, IndexError) as exc:
        logger.error("Failed to parse S3 event: %s", exc)
        return {"statusCode": 400, "body": "Invalid S3 event"}

    logger.info("Processing document: bucket=%s key=%s", bucket, key)

    # Get active giveaway year
    try:
        giveaway_year = _get_active_giveaway_year()
    except Exception:
        logger.exception("Failed to read active giveaway year")
        giveaway_year = str(datetime.now(timezone.utc).year)

    # Determine if this is a multi-page upload
    upload_prefix = _extract_upload_prefix(key)
    if upload_prefix:
        all_keys = _get_related_keys(bucket, upload_prefix)
    else:
        all_keys = [key]

    # Process each page through Textract
    page_results = []
    all_text_lines = []
    for page_key in all_keys:
        try:
            result = process_single_page(bucket, page_key)
            page_results.append(result)
            all_text_lines.extend(result.get("raw_text_lines", []))
        except ClientError as exc:
            logger.error("Textract failed for %s: %s", page_key, exc)
            # Store extraction_failed record
            _store_failed_record(bucket, key, giveaway_year, str(exc))
            return {"statusCode": 500, "body": "Textract extraction failed"}
        except Exception as exc:
            logger.exception("Unexpected error processing %s", page_key)
            _store_failed_record(bucket, key, giveaway_year, str(exc))
            return {"statusCode": 500, "body": "Processing failed"}

    if not page_results:
        logger.error("No pages processed for %s", key)
        _store_failed_record(bucket, key, giveaway_year, "No pages processed")
        return {"statusCode": 500, "body": "No pages processed"}

    # Merge multi-page results
    merged = merge_page_results(page_results)

    # Use overall language detection from all pages
    merged["detected_language"] = detect_language(all_text_lines)
    # Carry forward raw form fields from all pages
    all_raw = []
    for pr in page_results:
        all_raw.extend(pr.get("raw_form_fields", []))
    merged["raw_form_fields"] = all_raw

    # Build application record
    record, application_id = _build_application_record(
        merged, bucket, key, giveaway_year
    )

    logger.info(
        "Textract OCR complete: app_id=%s pages=%d language=%s",
        application_id,
        len(page_results),
        merged.get("detected_language", "en"),
    )

    # --- Stage 2: Bedrock interpretation ---
    try:
        record = run_bedrock_interpretation(record)
        logger.info(
            "Bedrock interpretation complete: app_id=%s status=%s "
            "overall_confidence=%.4f",
            application_id,
            record.get("status"),
            float(record.get("overall_confidence_score", 0)),
        )
    except Exception as exc:
        logger.exception("Bedrock interpretation failed for %s", application_id)
        # Mark as extraction_failed and store what we have
        record["status"] = "extraction_failed"
        record["processing_stage"] = "bedrock_failed"
        record["error_details"] = f"Bedrock interpretation failed: {str(exc)}"

    # --- Stage 3: Drawing extraction and analysis ---
    try:
        record = run_drawing_extraction(
            record, page_results, all_keys, bucket, giveaway_year
        )
        logger.info(
            "Drawing extraction complete: app_id=%s stage=%s",
            application_id,
            record.get("processing_stage"),
        )
    except Exception:
        logger.exception("Drawing extraction failed for %s", application_id)
        # Non-fatal: keep the record from previous stages
        record.setdefault("processing_stage", "drawing_failed")

    # Store in DynamoDB
    try:
        table_name = os.environ.get(
            "APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"
        )
        table = get_dynamodb_table(table_name)
        table.put_item(Item=_floats_to_decimals(record))
    except Exception:
        logger.exception("Failed to store application in DynamoDB")
        return {"statusCode": 500, "body": "Failed to store application"}

    # Record audit log entry
    try:
        log_audit_event(
            user_id="system",
            user_name="Document Processing Pipeline",
            action_type="create",
            resource_type="application",
            resource_id=application_id,
            details={
                "source_type": "upload",
                "giveaway_year": giveaway_year,
                "processing_stage": record.get("processing_stage", "bedrock_complete"),
                "detected_language": merged.get("detected_language", "en"),
                "pages_processed": len(page_results),
                "status": record.get("status"),
                "overall_confidence": str(record.get("overall_confidence_score", 0)),
            },
        )
    except Exception:
        logger.exception("Failed to record audit log entry")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "application_id": application_id,
            "processing_stage": record.get("processing_stage", "bedrock_complete"),
            "pages_processed": len(page_results),
            "detected_language": merged.get("detected_language", "en"),
            "status": record.get("status"),
            "overall_confidence_score": float(record.get("overall_confidence_score", 0)),
        }),
    }


def _store_failed_record(bucket, key, giveaway_year, error_msg):
    """Store an extraction_failed record in DynamoDB.

    Requirement 3.7: mark as extraction_failed and log error details.

    Args:
        bucket: S3 bucket name.
        key: S3 object key.
        giveaway_year: Giveaway year string.
        error_msg: Error message describing the failure.
    """
    application_id = generate_application_id()
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    record = {
        "application_id": application_id,
        "reference_number": "",
        "giveaway_year": giveaway_year,
        "submission_timestamp": timestamp,
        "source_type": "upload",
        "status": "extraction_failed",
        "overall_confidence_score": 0.0,
        "referring_agency": {},
        "parent_guardian": {},
        "children": [],
        "field_confidence": {},
        "original_documents": [{"s3_key": key, "upload_timestamp": timestamp}],
        "error_details": error_msg,
        "version": 1,
        "processing_stage": "textract_failed",
    }

    try:
        table_name = os.environ.get(
            "APPLICATIONS_TABLE_NAME", "bbp-hkbg-applications"
        )
        table = get_dynamodb_table(table_name)
        table.put_item(Item=_floats_to_decimals(record))
    except Exception:
        logger.exception("Failed to store extraction_failed record")

    try:
        log_audit_event(
            user_id="system",
            user_name="Document Processing Pipeline",
            action_type="create",
            resource_type="application",
            resource_id=application_id,
            details={
                "source_type": "upload",
                "giveaway_year": giveaway_year,
                "processing_stage": "textract_failed",
                "error": error_msg,
            },
        )
    except Exception:
        logger.exception("Failed to record audit log for failed extraction")
