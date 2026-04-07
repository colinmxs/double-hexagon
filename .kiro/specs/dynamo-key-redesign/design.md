# Design: DynamoDB Key Redesign & Human-Friendly Reference Numbers

## DynamoDB Table Schema

### Before
```
Table: bbp-hkbg-applications
  PK: giveaway_year (String)
  SK: application_id (String)
  GSI: status-index (giveaway_year + status)
  GSI: agency-index (giveaway_year + referring_agency_name)
```

### After
```
Table: bbp-hkbg-applications
  PK: application_id (String)        ← ULID, high cardinality
  GSI: year-index (giveaway_year + application_id)  ← for list/report queries
  GSI: status-index (giveaway_year + status)         ← unchanged
  GSI: agency-index (giveaway_year + referring_agency_name) ← unchanged
  GSI: reference-index (reference_number)            ← for lookup by human ID
```

## Reference Number Generation

Uses an atomic counter in the config table:

```python
# Config table item:
# { config_key: "next_ref_2025", value: 248 }

def generate_reference_number(giveaway_year):
    config_table = get_dynamodb_table("bbp-hkbg-config")
    response = config_table.update_item(
        Key={"config_key": f"next_ref_{giveaway_year}"},
        UpdateExpression="ADD #v :inc",
        ExpressionAttributeNames={"#v": "value"},
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="UPDATED_NEW",
    )
    seq = int(response["Attributes"]["value"])
    return f"APP-{giveaway_year}-{seq:04d}"
```

The `ADD` operation is atomic — safe for concurrent Lambda invocations.

## Application Record Shape

```json
{
  "application_id": "019668A3B2C4F8E7D6A5B4C3D2E1",
  "reference_number": "APP-2025-0247",
  "giveaway_year": "2025",
  "submission_timestamp": "...",
  "source_type": "digital",
  "status": "auto_approved",
  "referring_agency": { ... },
  "parent_guardian": { ... },
  "children": [ ... ],
  ...
}
```

## API Route Changes

| Before | After |
|--------|-------|
| `GET /api/applications?giveaway_year=2025` | unchanged |
| `GET /api/applications/{year}/{id}` | `GET /api/applications/{id}` |
| `PUT /api/applications/{year}/{id}` | `PUT /api/applications/{id}` |
| `PUT /api/applications/{id}/status` | unchanged |
| `PUT /api/applications/{id}/children/{childId}/bike-number` | unchanged |

## Frontend Route Changes

| Before | After |
|--------|-------|
| `/admin/review/:giveawayYear/:applicationId` | `/admin/review/:applicationId` |

## Handler Query Pattern Changes

| Operation | Before | After |
|-----------|--------|-------|
| Get single app | `table.get_item(Key={giveaway_year, application_id})` | `table.get_item(Key={application_id})` |
| Update app | `table.update_item(Key={giveaway_year, application_id})` | `table.update_item(Key={application_id})` |
| List by year | `table.query(PK=giveaway_year)` | `table.query(IndexName='year-index', PK=giveaway_year)` |
| Delete app | `table.delete_item(Key={giveaway_year, application_id})` | `table.delete_item(Key={application_id})` |

## Files Affected

### Infrastructure
- `infra/lib/storage-stack.ts` — table key schema + new GSIs
- `infra/test/storage-stack.test.ts` — key schema assertions

### Backend (Lambda handlers)
- `lambda/shared/utils.py` — add `generate_reference_number()`
- `lambda/submit_application/handler.py` — single-key write, generate reference_number
- `lambda/process_document/handler.py` — single-key write, generate reference_number
- `lambda/get_applications/handler.py` — query year-index GSI, include reference_number
- `lambda/get_application_detail/handler.py` — single-key GetItem
- `lambda/update_application/handler.py` — single-key UpdateItem
- `lambda/manage_giveaway_year/handler.py` — query year-index, single-key updates/deletes
- `lambda/run_report/handler.py` — query year-index
- `lambda/export_data/handler.py` — query year-index
- `lambda/local_api.py` — simplified routes
- `lambda/local_mock.py` — new table schema + seed reference_numbers

### Frontend
- `frontend/src/router/index.ts` — simplified route
- `frontend/src/views/ReviewListView.vue` — display reference_number, simplified navigation
- `frontend/src/views/ReviewDetailView.vue` — simplified route param, display reference_number
- `frontend/src/views/ApplyView.vue` — show reference_number on confirmation
- `frontend/src/App.vue` — no changes needed

### Tests
- All backend test files for affected handlers
- `frontend/src/views/__tests__/ReviewListView.spec.ts`
- `frontend/src/views/__tests__/ReviewDetailView.spec.ts`
- `frontend/src/views/__tests__/ApplyView.spec.ts`
