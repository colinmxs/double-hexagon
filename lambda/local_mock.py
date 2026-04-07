"""Moto-based mock AWS environment for local development.

When USE_MOTO=true, this module:
1. Starts moto mock services (DynamoDB, S3, Cognito, STS)
2. Creates all tables and buckets matching the CDK stack definitions
3. Seeds realistic test data for frontend development

Toggle: USE_MOTO=true|false (default: false)
"""

import os
import random
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# Add shared module to path so we can import generate_application_id
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))

# ---------------------------------------------------------------------------
# Table / bucket names (match handler defaults)
# ---------------------------------------------------------------------------
APPLICATIONS_TABLE = "bbp-hkbg-applications"
AUDIT_LOG_TABLE = "bbp-hkbg-audit-log"
USERS_TABLE = "bbp-hkbg-users"
SAVED_REPORTS_TABLE = "bbp-hkbg-saved-reports"
CONFIG_TABLE = "bbp-hkbg-config"
DOCUMENTS_BUCKET = "bbp-hkbg-documents"

REGION = "us-east-1"


def is_moto_enabled():
    return os.environ.get("USE_MOTO", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Table creation helpers
# ---------------------------------------------------------------------------

def _create_tables(dynamodb):
    """Create all DynamoDB tables matching the CDK storage stack."""

    # Applications table — PK: application_id (ULID), no sort key
    dynamodb.create_table(
        TableName=APPLICATIONS_TABLE,
        KeySchema=[
            {"AttributeName": "application_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "application_id", "AttributeType": "S"},
            {"AttributeName": "giveaway_year", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "referring_agency_name", "AttributeType": "S"},
            {"AttributeName": "reference_number", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "year-index",
                "KeySchema": [
                    {"AttributeName": "giveaway_year", "KeyType": "HASH"},
                    {"AttributeName": "application_id", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "status-index",
                "KeySchema": [
                    {"AttributeName": "giveaway_year", "KeyType": "HASH"},
                    {"AttributeName": "status", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "agency-index",
                "KeySchema": [
                    {"AttributeName": "giveaway_year", "KeyType": "HASH"},
                    {"AttributeName": "referring_agency_name", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "reference-index",
                "KeySchema": [
                    {"AttributeName": "reference_number", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Audit log table — PK: resource_id, SK: timestamp
    dynamodb.create_table(
        TableName=AUDIT_LOG_TABLE,
        KeySchema=[
            {"AttributeName": "resource_id", "KeyType": "HASH"},
            {"AttributeName": "timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "resource_id", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "user-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "timestamp", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Users table
    dynamodb.create_table(
        TableName=USERS_TABLE,
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "email-index",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Saved reports table
    dynamodb.create_table(
        TableName=SAVED_REPORTS_TABLE,
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "report_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "report_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Config table
    dynamodb.create_table(
        TableName=CONFIG_TABLE,
        KeySchema=[{"AttributeName": "config_key", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "config_key", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


# ---------------------------------------------------------------------------
# Seed data generators
# ---------------------------------------------------------------------------

AGENCIES = [
    {"agency_name": "Salvation Army", "contact_name": "Maria Lopez", "contact_phone": "555-0101", "contact_email": "maria@salvationarmy.example"},
    {"agency_name": "Boys & Girls Club", "contact_name": "James Wilson", "contact_phone": "555-0102", "contact_email": "james@bgclub.example"},
    {"agency_name": "United Way", "contact_name": "Sarah Chen", "contact_phone": "555-0103", "contact_email": "sarah@unitedway.example"},
    {"agency_name": "YMCA", "contact_name": "David Brown", "contact_phone": "555-0104", "contact_email": "david@ymca.example"},
    {"agency_name": "Habitat for Humanity", "contact_name": "Lisa Garcia", "contact_phone": "555-0105", "contact_email": "lisa@habitat.example"},
    {"agency_name": "Catholic Charities", "contact_name": "Robert Kim", "contact_phone": "555-0106", "contact_email": "robert@cathchar.example"},
]

FIRST_NAMES = ["Emma", "Liam", "Olivia", "Noah", "Ava", "Elijah", "Sophia", "Lucas", "Isabella", "Mason",
               "Mia", "Logan", "Charlotte", "Alexander", "Amelia", "Ethan", "Harper", "Aiden", "Evelyn", "Jackson"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
              "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
CITIES = ["Springfield", "Riverside", "Fairview", "Madison", "Georgetown", "Clinton", "Arlington", "Salem"]
ZIP_CODES = ["62701", "62702", "62703", "62704", "62705", "62706"]
LANGUAGES = ["English", "Spanish", "English", "English", "Spanish", "English"]
BIKE_COLORS = ["Red", "Blue", "Green", "Pink", "Purple", "Black", "White", "Orange", "Yellow"]
GENDERS = ["Male", "Female", "Non-binary"]
STATUSES = ["needs_review", "manually_approved", "rejected"]
STATUS_WEIGHTS = [50, 40, 10]
SOURCE_TYPES = ["digital", "upload"]
SOURCE_WEIGHTS = [60, 40]


def _random_child(index, giveaway_year, app_id):
    age = random.randint(4, 12)
    height = random.randint(36, 60)
    child_id = f"child-{index + 1:03d}"
    drawing_key = f"drawings/{giveaway_year}/{app_id}/{child_id}.png"
    return {
        "child_id": child_id,
        "first_name": random.choice(FIRST_NAMES),
        "last_name": random.choice(LAST_NAMES),
        "height_inches": Decimal(str(height)),
        "age": age,
        "gender": random.choice(GENDERS),
        "bike_color_1": random.choice(BIKE_COLORS),
        "bike_color_2": random.choice(BIKE_COLORS),
        "knows_how_to_ride": random.choice([True, False]),
        "other_siblings_enrolled": random.choice([True, False]),
        "drawing_image_s3_key": drawing_key,
        "drawing_keywords": random.sample(["fast", "cool", "sparkly", "big wheels", "basket", "bell", "streamers", "lights"], k=random.randint(1, 3)),
        "dream_bike_description": None,
        "bike_number": None,
    }


def _random_application(giveaway_year, app_index, base_time):
    from utils import generate_application_id

    app_id = generate_application_id()
    reference_number = f"{giveaway_year}-{app_index:04d}"
    agency = random.choice(AGENCIES)
    # Past years are fully resolved — mostly approved, a few rejected
    if giveaway_year in ("2024", "2025"):
        status = random.choices(
            ["manually_approved", "rejected"],
            weights=[85, 15],
            k=1,
        )[0]
    else:
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
    source_type = random.choices(SOURCE_TYPES, weights=SOURCE_WEIGHTS, k=1)[0]
    num_children = random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5], k=1)[0]
    parent_last = random.choice(LAST_NAMES)
    parent_first = random.choice(FIRST_NAMES)
    lang = random.choice(LANGUAGES)

    offset = timedelta(hours=random.randint(0, 720))
    ts = (base_time - offset).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    confidence = Decimal(str(round(random.uniform(0.6, 1.0), 2))) if source_type == "upload" else Decimal("1.0")

    return {
        "giveaway_year": giveaway_year,
        "application_id": app_id,
        "reference_number": reference_number,
        "submission_timestamp": ts,
        "source_type": source_type,
        "status": status,
        "overall_confidence_score": confidence,
        "referring_agency": agency,
        "referring_agency_name": agency["agency_name"],
        "parent_guardian": {
            "first_name": parent_first,
            "last_name": parent_last,
            "address": f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Elm', 'Cedar', 'Pine', 'Maple'])} St",
            "city": random.choice(CITIES),
            "zip_code": random.choice(ZIP_CODES),
            "phone": f"555-{random.randint(1000, 9999)}",
            "email": f"{parent_first.lower()}.{parent_last.lower()}@example.com",
            "primary_language": lang,
            "english_speaker_in_household": True,
            "preferred_contact_method": random.choice(["phone", "email", "text"]),
            "transportation_access": random.choice([True, False]),
        },
        "children": [_random_child(i, giveaway_year, app_id) for i in range(num_children)],
        "field_confidence": {},
        "original_documents": [
            {
                "s3_key": f"uploads/{giveaway_year}/{app_id}/page1.pdf",
                "upload_timestamp": ts,
            }
        ] if source_type == "upload" else [],
        "version": 1,
    }


def _seed_data(dynamodb, s3_client):
    """Populate tables with realistic test data."""
    now = datetime.now(timezone.utc)

    # --- Config ---
    config_table = dynamodb.Table(CONFIG_TABLE)
    config_table.put_item(Item={"config_key": "active_giveaway_year", "value": "2026"})
    config_table.put_item(Item={"config_key": "confidence_threshold", "value": Decimal("0.85")})

    # --- Users ---
    users_table = dynamodb.Table(USERS_TABLE)
    users = [
        {"user_id": "sarah.m", "email": "sarah.m@greenfield.org", "name": "Sarah Mitchell", "role": "admin", "status": "active", "last_login": (now - timedelta(minutes=12)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "james.w", "email": "james.w@greenfield.org", "name": "James Wilson", "role": "admin", "status": "active", "last_login": (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "maria.g", "email": "maria.g@greenfield.org", "name": "Maria Garcia", "role": "admin", "status": "active", "last_login": (now - timedelta(days=1, hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "david.c", "email": "david.c@greenfield.org", "name": "David Chen", "role": "reporter", "status": "active", "last_login": (now - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "lisa.t", "email": "lisa.t@greenfield.org", "name": "Lisa Thompson", "role": "reporter", "status": "active", "last_login": (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "mike.r", "email": "mike.r@greenfield.org", "name": "Mike Robinson", "role": "submitter", "status": "active", "last_login": (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "anna.k", "email": "anna.k@greenfield.org", "name": "Anna Kim", "role": "submitter", "status": "active", "last_login": (now - timedelta(days=2, hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "tom.b", "email": "tom.b@greenfield.org", "name": "Tom Brooks", "role": "submitter", "status": "active", "last_login": (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "rachel.n", "email": "rachel.n@greenfield.org", "name": "Rachel Nguyen", "role": "reporter", "status": "disabled", "last_login": (now - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "chris.d", "email": "chris.d@greenfield.org", "name": "Chris Davis", "role": "admin", "status": "disabled", "last_login": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"user_id": "jrod", "email": "jrod@greenfield.org", "name": "J-Rod", "role": "submitter", "status": "active", "last_login": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")},
    ]
    for u in users:
        users_table.put_item(Item=u)

    # --- Applications: 120 for 2026 (current), 150 for 2025, 80 for 2024 ---
    apps_table = dynamodb.Table(APPLICATIONS_TABLE)
    for i in range(700):
        apps_table.put_item(Item=_random_application("2026", i + 1, now))
    for i in range(150):
        apps_table.put_item(Item=_random_application("2025", i + 1, now - timedelta(days=365)))
    for i in range(80):
        apps_table.put_item(Item=_random_application("2024", i + 1, now - timedelta(days=730)))

    # --- Atomic counters for reference number generation ---
    config_table.put_item(Item={"config_key": "next_ref_2026", "value": 701})
    config_table.put_item(Item={"config_key": "next_ref_2025", "value": 151})
    config_table.put_item(Item={"config_key": "next_ref_2024", "value": 81})

    # --- Giveaway years in config ---
    config_table.put_item(Item={
        "config_key": "giveaway_years",
        "value": [
            {"year": "2026", "status": "active"},
            {"year": "2025", "status": "archived"},
            {"year": "2024", "status": "archived"},
        ],
    })

    # --- Saved reports ---
    reports_table = dynamodb.Table(SAVED_REPORTS_TABLE)
    reports_table.put_item(Item={
        "user_id": "sarah.m",
        "report_id": f"rpt-{uuid.uuid4().hex[:8]}",
        "name": "Height Distribution",
        "columns": ["status", "children.height_inches"],
        "filters": [],
        "group_by": "children.height_inches",
        "sort_by": None,
        "sort_order": "asc",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    })

    # --- Audit log entries ---
    audit_table = dynamodb.Table(AUDIT_LOG_TABLE)
    app_ids = [f"2026-{i:04d}" for i in range(1, 21)] + [f"2025-{i:04d}" for i in range(1, 11)]

    sample_changes = [
        [{"field_name": "parent_guardian.phone", "previous_value": "555-0101", "new_value": "555-9999"}],
        [{"field_name": "parent_guardian.last_name", "previous_value": "Gracia", "new_value": "Garcia"}],
        [{"field_name": "status", "previous_value": "needs_review", "new_value": "manually_approved"}],
        [
            {"field_name": "parent_guardian.address", "previous_value": "123 Main St", "new_value": "456 Oak Ave"},
            {"field_name": "parent_guardian.city", "previous_value": "Springfeld", "new_value": "Springfield"},
            {"field_name": "parent_guardian.zip_code", "previous_value": "62701", "new_value": "62704"},
        ],
        [{"field_name": "children[0].height_inches", "previous_value": "46", "new_value": "48"}],
        [
            {"field_name": "children[0].bike_color_1", "previous_value": "Red", "new_value": "Blue"},
            {"field_name": "children[0].bike_color_2", "previous_value": "White", "new_value": "Black"},
        ],
        [{"field_name": "children[0].bike_number", "previous_value": None, "new_value": "B-2025-042"}],
        [{"field_name": "referring_agency.contact_phone", "previous_value": "555-0100", "new_value": "555-0200"}],
    ]

    for i in range(100):
        offset = timedelta(hours=random.randint(0, 720))
        ts = (now - offset)
        timestamp_str = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{random.randint(0,999):03d}Z"
        user = random.choice(users)
        resource_id = random.choice(app_ids)
        action = random.choice(["create", "update", "update", "view", "view", "export"])

        details: dict = {}
        if action == "update":
            details = {"changes": random.choice(sample_changes)}
        elif action == "create":
            details = {"source_type": random.choice(["digital", "upload"])}
        elif action == "export":
            details = {"export_type": random.choice(["bike_build_list", "family_contact_list"])}

        audit_table.put_item(Item={
            "resource_id": resource_id,
            "timestamp": timestamp_str,
            "user_id": user["user_id"],
            "user_name": user["name"],
            "action_type": action,
            "resource_type": "application",
            "details": details,
        })

    # --- S3 bucket + fixture images ---
    s3_client.create_bucket(Bucket=DOCUMENTS_BUCKET)

    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    bike_path = os.path.join(fixtures_dir, "bike.png")
    form_path = os.path.join(fixtures_dir, "form.jpg")

    # Read fixture files once
    bike_bytes = open(bike_path, "rb").read() if os.path.exists(bike_path) else None
    form_bytes = open(form_path, "rb").read() if os.path.exists(form_path) else None

    # Seed S3 with images for every application
    if bike_bytes or form_bytes:
        all_apps_table = dynamodb.Table(APPLICATIONS_TABLE)
        scan = all_apps_table.scan(ProjectionExpression="application_id, giveaway_year, children, source_type, original_documents")
        items = scan.get("Items", [])
        while scan.get("LastEvaluatedKey"):
            scan = all_apps_table.scan(
                ProjectionExpression="application_id, giveaway_year, children, source_type, original_documents",
                ExclusiveStartKey=scan["LastEvaluatedKey"],
            )
            items.extend(scan.get("Items", []))

        for app in items:
            # Upload bike drawing for each child
            if bike_bytes:
                for child in app.get("children", []):
                    key = child.get("drawing_image_s3_key")
                    if key:
                        s3_client.put_object(Bucket=DOCUMENTS_BUCKET, Key=key, Body=bike_bytes, ContentType="image/png")

            # Upload form image for upload-type applications
            if form_bytes and app.get("source_type") == "upload":
                for doc in app.get("original_documents", []):
                    key = doc.get("s3_key")
                    if key:
                        s3_client.put_object(Bucket=DOCUMENTS_BUCKET, Key=key, Body=form_bytes, ContentType="image/jpeg")

    print(f"Seeded: 930 applications (2024-2026), {len(users)} users, 100 audit entries, 1 saved report")


# ---------------------------------------------------------------------------
# Main entry point — call this before starting Flask
# ---------------------------------------------------------------------------

_moto_mocks = []


def start_moto():
    """Start moto mocks and seed data. Call once before Flask app starts."""
    from moto import mock_aws

    mock = mock_aws()
    mock.start()
    _moto_mocks.append(mock)

    os.environ["AWS_DEFAULT_REGION"] = REGION
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

    import boto3
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    s3_client = boto3.client("s3", region_name=REGION)

    _create_tables(dynamodb)
    _seed_data(dynamodb, s3_client)

    print("Moto mock AWS environment started and seeded.")


def stop_moto():
    """Stop moto mocks. Call on shutdown."""
    for mock in _moto_mocks:
        mock.stop()
    _moto_mocks.clear()
