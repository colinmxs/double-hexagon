# Requirements: DynamoDB Key Redesign & Human-Friendly Reference Numbers

## Background
The applications table currently uses `giveaway_year` as the partition key, creating a hot partition during bulk OCR uploads (100+ concurrent writes). The application ID shown to users is a 28-character hex ULID, which is impractical for families and staff.

## Requirements

### R1: Table Key Restructure
- R1.1: Change the applications table partition key to `application_id` (ULID, no sort key)
- R1.2: Add a GSI `year-index` with `giveaway_year` as PK and `application_id` as SK for list/report queries
- R1.3: Keep existing GSIs (`status-index`, `agency-index`) unchanged — they already use `giveaway_year` as PK
- R1.4: Update the CDK storage stack and its tests to reflect the new key schema

### R2: Human-Friendly Reference Number
- R2.1: Add a `reference_number` attribute to each application record (format: `APP-{year}-{sequential}`, e.g. `APP-2025-0247`)
- R2.2: Generate sequential numbers using an atomic counter in the config table, scoped per giveaway year
- R2.3: The internal `application_id` (ULID) remains the DynamoDB partition key — `reference_number` is display-only
- R2.4: Add a GSI `reference-index` with `reference_number` as PK for lookup by reference number

### R3: Backend Handler Updates
- R3.1: Update all handlers that do `GetItem`/`UpdateItem`/`DeleteItem` to use single-key `{application_id}` instead of composite `{giveaway_year, application_id}`
- R3.2: Update all handlers that list/query by year to use `IndexName='year-index'`
- R3.3: Update `submit_application` and `process_document` to generate and store `reference_number`
- R3.4: Include `reference_number` in all API responses that return application data
- R3.5: Update pagination tokens to use single-key format

### R4: API Route Simplification
- R4.1: Simplify detail/update routes from `/api/applications/{giveaway_year}/{application_id}` to `/api/applications/{application_id}`
- R4.2: Keep `giveaway_year` as a query parameter for list endpoints
- R4.3: Update `local_api.py` Flask routes to match

### R5: Frontend Updates
- R5.1: Display `reference_number` instead of `application_id` everywhere users see it (review list, detail view, confirmation pages, exports)
- R5.2: Simplify the router from `/admin/review/:giveawayYear/:applicationId` to `/admin/review/:applicationId`
- R5.3: Update all frontend API calls to use the simplified routes
- R5.4: Update the apply confirmation page to show the human-friendly reference number

### R6: Local Dev & Tests
- R6.1: Update `local_mock.py` table creation to match new key schema
- R6.2: Update seed data to include `reference_number` on all seeded applications
- R6.3: Update all backend tests for new key structure
- R6.4: Update all frontend tests for new route structure and reference_number display
- R6.5: Update CDK infrastructure tests
