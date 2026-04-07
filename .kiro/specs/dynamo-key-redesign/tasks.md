# Tasks: DynamoDB Key Redesign & Human-Friendly Reference Numbers

## Task 1: Update CDK storage stack
- [x] Change applications table PK to `application_id` (remove sort key)
- [x] Add `year-index` GSI with `giveaway_year` PK + `application_id` SK
- [x] Add `reference-index` GSI with `reference_number` PK
- [x] Keep existing `status-index` and `agency-index` GSIs unchanged
- [x] Update `infra/test/storage-stack.test.ts` for new key schema
- [x] Run `cd infra && npm test` — storage and related tests pass
#[[file:infra/lib/storage-stack.ts]]
#[[file:infra/test/storage-stack.test.ts]]

## Task 2: Add reference number generator to shared utils
- [x] Add `generate_reference_number(giveaway_year)` to `lambda/shared/utils.py`
- [x] Uses atomic counter in config table (`next_ref_{year}` key with `ADD` operation)
- [x] Format: `APP-{year}-{seq:04d}`
- [x] Add tests in `lambda/shared/test_utils.py`
#[[file:lambda/shared/utils.py]]
#[[file:lambda/shared/test_utils.py]]

## Task 3: Update submit_application handler
- [x] Write with single-key `{application_id}` instead of composite key
- [x] Generate and store `reference_number` on the application record
- [x] Return `reference_number` in the API response
- [x] Update tests
#[[file:lambda/submit_application/handler.py]]
#[[file:lambda/submit_application/test_handler.py]]

## Task 4: Update process_document handler
- [x] Write with single-key `{application_id}`
- [ ] Generate and store `reference_number` on the application record
- [ ] Update tests
#[[file:lambda/process_document/handler.py]]
#[[file:lambda/process_document/test_handler.py]]

## Task 5: Update get_applications handler
- [x] Query `year-index` GSI instead of base table for list-by-year
- [x] Include `reference_number` in response items
- [x] Update pagination token format (single key)
- [ ] Update tests
#[[file:lambda/get_applications/handler.py]]
#[[file:lambda/get_applications/test_handler.py]]

## Task 6: Update get_application_detail handler
- [x] Use single-key `GetItem` with `{application_id}`
- [x] Remove requirement for `giveaway_year` path param
- [x] Include `reference_number` in response
- [ ] Update tests
#[[file:lambda/get_application_detail/handler.py]]
#[[file:lambda/get_application_detail/test_handler.py]]

## Task 7: Update update_application handler
- [x] Use single-key `UpdateItem`/`GetItem` with `{application_id}`
- [ ] Update tests
#[[file:lambda/update_application/handler.py]]
#[[file:lambda/update_application/test_handler.py]]

## Task 8: Update manage_giveaway_year handler
- [x] Query `year-index` GSI for listing applications by year
- [x] Use single-key for update/delete operations on individual items
- [ ] Update tests
#[[file:lambda/manage_giveaway_year/handler.py]]
#[[file:lambda/manage_giveaway_year/test_handler.py]]

## Task 9: Update run_report and export_data handlers
- [x] Query `year-index` GSI instead of base table
- [ ] Update tests
#[[file:lambda/run_report/handler.py]]
#[[file:lambda/run_report/test_handler.py]]
#[[file:lambda/export_data/handler.py]]
#[[file:lambda/export_data/test_handler.py]]

## Task 10: Update API routes
- [x] Simplify `local_api.py` routes: remove `giveaway_year` from detail/update paths
- [x] Update CDK `api-stack.ts` API Gateway resource paths
- [x] Update `infra/test/api-stack.test.ts`
#[[file:lambda/local_api.py]]
#[[file:infra/lib/api-stack.ts]]
#[[file:infra/test/api-stack.test.ts]]

## Task 11: Update local mock and seed data
- [x] Update `local_mock.py` table creation to new key schema (PK: application_id, GSIs)
- [x] Update seed data to use ULID application_ids and include `reference_number`
- [x] Seed the atomic counter in config table
#[[file:lambda/local_mock.py]]

## Task 12: Update frontend router and views
- [x] Simplify router: `/admin/review/:applicationId` (remove giveawayYear param)
- [x] Update `ReviewListView.vue`: display `reference_number`, simplify navigation link
- [x] Update `ReviewDetailView.vue`: use simplified route, display `reference_number`
- [x] Update `ApplyView.vue`: show `reference_number` on confirmation page
- [x] Update all frontend tests
#[[file:frontend/src/router/index.ts]]
#[[file:frontend/src/views/ReviewListView.vue]]
#[[file:frontend/src/views/ReviewDetailView.vue]]
#[[file:frontend/src/views/ApplyView.vue]]
#[[file:frontend/src/views/__tests__/ReviewListView.spec.ts]]
#[[file:frontend/src/views/__tests__/ReviewDetailView.spec.ts]]
#[[file:frontend/src/views/__tests__/ApplyView.spec.ts]]

## Task 13: Full test pass
- [x] Run `cd infra && npm test` — all 49 tests pass
- [x] Run `cd frontend && npx vitest run` — all 104 tests pass
- [x] Run `python -m pytest lambda/` — all backend tests pass
- [x] Run `cd frontend && npm run build` — build succeeds
