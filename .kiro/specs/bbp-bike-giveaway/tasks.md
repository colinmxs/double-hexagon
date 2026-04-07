# Implementation Plan: BBP Holiday Kids Bike Giveaway System

## Overview

This plan implements a serverless web application for the Boise Bicycle Project's Holiday Kids Bike Giveaway. Infrastructure is built first (CDK), followed by auth bypass for local dev, backend Lambdas (Python), frontend Vue.js components, the AI processing pipeline, admin dashboard features, CI/CD, and security hardening. Data security (PII of minors) is the top priority throughout.

## Tasks

- [x] 1. CDK Storage Stack — S3 buckets and DynamoDB tables
  - [x] 1.1 Create CDK project scaffolding and Storage Stack with S3 buckets
    - Initialize CDK app in TypeScript with `cdk init`
    - Create `StorageStack` with two S3 buckets: `bbp-hkbg-documents` (uploads, drawings, versions, exports prefixes; lifecycle rule for Glacier transition; Block Public Access enabled; SSE-S3 encryption) and `bbp-hkbg-static` (static site hosting)
    - _Requirements: 8.1, 9.3, 16.2, 16.5_
    - _Agent Skills: `aws-cdk-development`, `s3`_

  - [x] 1.2 Add DynamoDB tables to Storage Stack
    - Create 5 DynamoDB tables: Applications (PK: giveaway_year, SK: application_id, GSIs: status-index, agency-index), Audit Log (PK: year_month, SK: timestamp#user_id, GSIs: user-index, action-index), Users (PK: user_id, GSI: email-index), Saved Reports (PK: user_id, SK: report_id), Config (PK: config_key)
    - Enable encryption at rest on all tables
    - _Requirements: 9.1, 9.2, 15.10, 16.1_
    - _Agent Skills: `aws-cdk-development`, `dynamodb`_

  - [x] 1.3 Write unit tests for Storage Stack
    - Test S3 bucket encryption and Block Public Access settings
    - Test DynamoDB table key schemas, GSIs, and encryption
    - _Requirements: 16.1, 16.2, 16.5_
    - _Agent Skills: `aws-cdk-development`, `s3`, `dynamodb`_

- [x] 2. CDK Auth Stack — Cognito User Pool with Google federation
  - [x] 2.1 Create Auth Stack with Cognito User Pool
    - Create `AuthStack` that depends on `StorageStack`
    - Configure Cognito User Pool with native username/password sign-in and Google as federated identity provider
    - Create App Client for the SPA with OAuth 2.0 / OIDC configuration
    - Configure password policies and hosted UI redirect flow
    - Export User Pool ID and App Client ID for downstream stacks
    - _Requirements: 8.3, 14.2, 14.9, 16.7_
    - _Agent Skills: `aws-cdk-development`, `cognito`_

  - [x] 2.2 Write unit tests for Auth Stack
    - Test Cognito User Pool configuration, Google IdP, App Client settings
    - _Requirements: 8.3_
    - _Agent Skills: `aws-cdk-development`, `cognito`_

- [x] 3. CDK API Stack — API Gateway, Lambda functions, and IAM roles
  - [x] 3.1 Create API Stack with API Gateway and Cognito authorizer
    - Create `ApiStack` that depends on `StorageStack` and `AuthStack`
    - Define REST API with Cognito User Pool authorizer on authenticated endpoints
    - Configure rate limiting on public endpoints (submit application, upload presign)
    - Set up CORS configuration
    - _Requirements: 8.2, 16.7, 16.8_
    - _Agent Skills: `aws-cdk-development`, `api-gateway`, `cognito`_

  - [x] 3.2 Define all Lambda functions with least-privilege IAM roles
    - Create Lambda function definitions for all 14 backend functions (Python runtime)
    - Create per-Lambda IAM roles with scoped permissions — no wildcard resources
    - Pass environment variables for table names, bucket names, and `AUTH_ENABLED`
    - Configure S3 event notification on uploads prefix to trigger `process_document` Lambda
    - _Requirements: 8.2, 16.6, 16.12_
    - _Agent Skills: `aws-cdk-development`, `lambda`, `iam`, `s3`_

  - [x] 3.3 Write unit tests for API Stack
    - Test API Gateway routes, authorizer config, rate limiting
    - Test Lambda IAM role policies have no wildcard resources
    - _Requirements: 16.6, 16.8, 16.12_
    - _Agent Skills: `aws-cdk-development`, `api-gateway`, `iam`, `lambda`_

- [x] 4. CDK Frontend Stack and CI/CD Stack
  - [x] 4.1 Create Frontend Stack with S3 and CloudFront
    - Create `FrontendStack` that depends on `StorageStack` and `ApiStack`
    - Configure CloudFront distribution with S3 static site origin, HTTPS-only, custom error pages for SPA routing
    - Export CloudFront distribution URL
    - _Requirements: 8.1, 8.4, 16.4_
    - _Agent Skills: `aws-cdk-development`, `s3`_

  - [x] 4.2 Create CI/CD Stack with GitHub Actions OIDC IAM role
    - Create `CiCdStack` with IAM role for GitHub Actions OIDC federation
    - Scope CI/CD role to deployment-only permissions — no administrative or data-read permissions
    - _Requirements: 12.8, 16.13_
    - _Agent Skills: `aws-cdk-development`, `iam`_

  - [x] 4.3 Write unit tests for Frontend and CI/CD Stacks
    - Test CloudFront HTTPS-only, SPA error pages
    - Test CI/CD IAM role has no data-read or admin permissions
    - _Requirements: 16.4, 16.13_
    - _Agent Skills: `aws-cdk-development`, `iam`_

- [x] 5. Checkpoint — CDK infrastructure
  - Ensure all CDK stacks synthesize without errors and all tests pass, ask the user if questions arise.

- [x] 6. Auth bypass for local development
  - [x] 6.1 Implement backend auth bypass middleware (Python)
    - Create shared auth middleware that checks `AUTH_ENABLED` environment variable
    - When `AUTH_ENABLED=false`, skip Cognito token validation and inject hardcoded local admin user identity into request context
    - When `AUTH_ENABLED=true`, validate Cognito JWT token and extract user identity
    - Look up user role from DynamoDB Users table and attach to request context
    - _Requirements: 8.3, 14.10_
    - _Agent Skills: `cognito`, `lambda`, `dynamodb`_

  - [x] 6.2 Implement role-based access control enforcement (Python)
    - Create RBAC decorator/middleware that checks user role against endpoint permissions
    - Enforce giveaway year scoping for reporter role
    - Return 403 for unauthorized access attempts
    - _Requirements: 14.3, 14.6, 14.10_
    - _Agent Skills: `lambda`, `iam`_

  - [x] 6.3 Write unit tests for auth middleware and RBAC
    - Test auth bypass when AUTH_ENABLED=false
    - Test JWT validation when AUTH_ENABLED=true
    - Test role-based access control for admin, reporter, submitter
    - Test reporter giveaway year scoping
    - _Requirements: 14.3, 14.6, 14.10_
    - _Agent Skills: `lambda`, `cognito`_

- [x] 7. Backend — Audit logging middleware and core utilities (Python)
  - [x] 7.1 Implement audit logging middleware
    - Create `audit_middleware` module that writes audit log entries to the Audit Log DynamoDB table
    - Record: user_id, user_name, timestamp, action_type (view/create/update/delete/export/login/logout), resource_type, resource_id, details (field name, previous value, new value for updates)
    - Ensure PII values are NOT logged in CloudWatch Logs
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 16.10_
    - _Agent Skills: `lambda`, `dynamodb`, `cloudwatch`_

  - [x] 7.2 Implement shared backend utilities
    - Create DynamoDB client helpers, S3 pre-signed URL generator (15-min expiry), response formatters, error handling (no PII in error responses)
    - Create ULID generator for application IDs
    - _Requirements: 9.4, 16.9, 16.10_
    - _Agent Skills: `lambda`, `dynamodb`, `s3`_

  - [x] 7.3 Write unit tests for audit middleware and utilities
    - Test audit log entry creation with all action types
    - Test pre-signed URL expiry is 15 minutes
    - Test error responses contain no PII
    - _Requirements: 15.1, 16.9, 16.10_
    - _Agent Skills: `lambda`, `dynamodb`, `s3`_

- [x] 8. Backend — Application submission and upload Lambda functions (Python)
  - [x] 8.1 Implement `submit_application` Lambda
    - Accept POST request with digital form data
    - Validate all required fields (child height in inches mandatory)
    - Store application in DynamoDB with confidence 1.0 for all fields, tagged with active giveaway year
    - Set status to "auto_approved" (digital submissions are fully trusted)
    - Record audit log entry for create action
    - _Requirements: 1.3, 1.4, 9.1, 17.12_
    - _Agent Skills: `lambda`, `dynamodb`, `api-gateway`_

  - [x] 8.2 Implement `generate_presigned_url` Lambda
    - Accept POST request with file metadata (name, type, size)
    - Validate file type (PDF, PNG, JPEG) and size (≤10MB)
    - Generate pre-signed S3 PUT URL with 15-minute expiry
    - Return pre-signed URL and reference identifier
    - _Requirements: 2.1, 2.2, 2.3, 2.7, 16.9_
    - _Agent Skills: `lambda`, `s3`, `api-gateway`_

  - [x] 8.3 Write unit tests for submission and upload Lambdas
    - Test required field validation
    - Test confidence 1.0 assignment for digital submissions
    - Test file type/size validation
    - Test pre-signed URL generation
    - _Requirements: 1.3, 1.4, 2.1, 2.2_
    - _Agent Skills: `lambda`, `dynamodb`, `s3`_

- [x] 9. Backend — Application review and management Lambda functions (Python)
  - [x] 9.1 Implement `get_applications` Lambda
    - Query applications by giveaway year with optional filters (status, search by family name or agency name)
    - Enforce giveaway year scoping for reporter role
    - Return paginated list with family name, date, source, status, confidence score, drawing thumbnail URL
    - _Requirements: 5.1, 5.2, 5.3, 14.6, 17.3_
    - _Agent Skills: `lambda`, `dynamodb`, `api-gateway`_

  - [x] 9.2 Implement `get_application_detail` Lambda
    - Return full application record with all fields, per-field confidence scores, original document pre-signed URLs, and drawing image URLs
    - Record audit log entry for view action
    - _Requirements: 5.4, 5.6, 9.1, 9.2, 15.2_
    - _Agent Skills: `lambda`, `dynamodb`, `s3`_

  - [x] 9.3 Implement `update_application` Lambda
    - Accept field updates, set edited field confidence to 1.0
    - Support status updates (manually_approved), bike number assignment, drawing keywords editing
    - Retain previous version for audit (store in S3)
    - Record audit log entry with field name, previous value, new value
    - _Requirements: 5.7, 5.8, 5.9, 5.10, 5.11, 9.2, 15.3_
    - _Agent Skills: `lambda`, `dynamodb`, `s3`_

  - [x] 9.4 Write unit tests for application review Lambdas
    - Test filtering, search, pagination
    - Test confidence reset to 1.0 on edit
    - Test version retention
    - Test audit log recording
    - _Requirements: 5.1, 5.7, 9.2, 15.3_
    - _Agent Skills: `lambda`, `dynamodb`_

- [x] 10. Backend — Export Lambda functions (Python)
  - [x] 10.1 Implement `export_data` Lambda
    - Generate Bike Build List CSV: child first name, last name, height, age, gender, bike color 1, bike color 2, knows how to ride, Dream_Bike_Description, Drawing_Keywords, Bike_Number
    - Generate Family Contact List CSV: parent/guardian first name, last name, phone, email, address, city, zip, primary language, preferred contact method, transportation access, referring agency name
    - Support status filter for which applications to include
    - Include header row with descriptive column names
    - Record audit log entry for export action with filters applied
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 10.5, 15.5_
    - _Agent Skills: `lambda`, `dynamodb`_

  - [x] 10.2 Write unit tests for export Lambda
    - Test CSV column headers and content for both export types
    - Test status filtering
    - _Requirements: 6.1, 6.2, 6.3, 6.5_
    - _Agent Skills: `lambda`, `dynamodb`_

- [x] 11. Checkpoint — Core backend Lambdas
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Frontend — Vue.js project setup, i18n, shared components
  - [x] 12.1 Initialize Vue.js project with TypeScript and configure i18n
    - Create Vue 3 + TypeScript project with Vite
    - Install and configure Vue i18n with English (`en.json`) and Spanish (`es.json`) locale files
    - All user-facing strings must use codenames: "Greenfield Foundation" for the organization, "Community Gift Program" for the event — no references to the real organization or event name in frontend UI text
    - Implement browser language detection to default to matching supported language
    - _Requirements: 7.1, 7.4_
    - _Agent Skills: `vue-best-practices`_

  - [x] 12.2 Implement shared components
    - `LanguageToggle`: Switches locale, persists preference to localStorage, visible on all pages
    - `ConfidenceBadge`: Color-coded indicator (green ≥ threshold, yellow near, red below)
    - `DrawingViewer`: Displays Drawing_Image with keyword tags
    - `SessionTimeout`: Auto-logout after 30 minutes of inactivity
    - `AuthGuard`: Route guard checking Cognito session + DynamoDB role; bypasses all checks when `AUTH_ENABLED=false`
    - _Requirements: 7.2, 7.3, 5.9, 16.11_
    - _Agent Skills: `vue-best-practices`, `create-adaptable-composable`_

  - [x] 12.3 Set up Vue Router with auth-guarded routes
    - Define routes: `/apply` (public), `/upload` (public), `/admin` (auth-guarded with role checks), `/admin/review`, `/admin/reports`, `/admin/cost`, `/admin/users`, `/admin/audit`, `/admin/years`
    - Implement AuthGuard integration with route meta for role requirements
    - _Requirements: 14.1, 14.3, 14.11_
    - _Agent Skills: `vue-best-practices`, `vue-router-best-practices`_

  - [x] 12.4 Write unit tests for shared components
    - Test LanguageToggle switches locale without page reload
    - Test ConfidenceBadge color thresholds
    - Test SessionTimeout triggers logout after 30 minutes
    - Test AuthGuard bypass when AUTH_ENABLED=false
    - _Requirements: 7.2, 7.3, 16.11_
    - _Agent Skills: `vue-testing-best-practices`, `vue-best-practices`_

- [x] 13. Frontend — Digital Application Form (`/apply`)
  - [x] 13.1 Implement Digital Application Form component
    - Build multi-section form: Referring Agency Info → Parent/Guardian Info → Child Info (repeatable, add/remove children) → Dream Bike Drawing upload per child
    - All field labels, instructions, and validation messages in both English and Spanish via i18n
    - Client-side validation: all required fields, height as numeric inches, file type/size for drawing uploads
    - Display training wheels note in Child Information section
    - Dream Bike Description text area per child
    - Responsive layout targeting 320px minimum width
    - Submit to REST API; accept input in any language regardless of interface language
    - Display confirmation with reference ID on success
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 7.4, 17.12_
    - _Agent Skills: `vue-best-practices`_

  - [x] 13.2 Write unit tests for Digital Application Form
    - Test required field validation
    - Test multi-child add/remove
    - Test responsive rendering at 320px
    - Test bilingual labels
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_
    - _Agent Skills: `vue-testing-best-practices`_

- [x] 14. Frontend — Upload Portal (`/upload`)
  - [x] 14.1 Implement Upload Portal component
    - Drag-and-drop + file picker for PDF, PNG, JPEG (max 10MB per file)
    - Multi-file upload support for multi-page applications
    - Client-side file type and size validation with error messages specifying limits and accepted formats
    - Request pre-signed URL from API, upload directly to S3
    - Display confirmation with reference ID on success
    - Bilingual instructions (English/Spanish)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
    - _Agent Skills: `vue-best-practices`, `s3`_

  - [x] 14.2 Write unit tests for Upload Portal
    - Test file type/size validation and error messages
    - Test multi-file upload flow
    - _Requirements: 2.1, 2.2, 2.7_
    - _Agent Skills: `vue-testing-best-practices`_

- [x] 15. Frontend — Admin Dashboard application list and review views
  - [x] 15.1 Implement Application List View
    - Sortable/filterable table: family name, submission date, source, status, confidence score, drawing thumbnail
    - Filter by status, search by family name or agency name
    - Default to active giveaway year
    - Allow switching between giveaway years
    - _Requirements: 5.1, 5.2, 5.3, 10.4, 17.3, 17.4_
    - _Agent Skills: `vue-best-practices`_

  - [x] 15.2 Implement Side-by-Side Review View
    - Original document viewer (multi-page navigation) on left
    - Editable transcription form on right with per-field ConfidenceBadge
    - Low-confidence fields visually highlighted
    - Save edits (confidence resets to 1.0), approve application (status → manually_approved)
    - Display Drawing_Image with Drawing_Keywords, allow keyword editing
    - Bike_Number assignment field per child
    - Dream_Bike_Description display and editing
    - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 10.4, 10.6, 10.8_
    - _Agent Skills: `vue-best-practices`_

  - [x] 15.3 Write unit tests for application list and review views
    - Test filtering and search
    - Test confidence badge display
    - Test edit saves and confidence reset
    - _Requirements: 5.1, 5.7, 5.9_
    - _Agent Skills: `vue-testing-best-practices`_

- [x] 16. Frontend — Data Export UI
  - [x] 16.1 Implement export controls in Admin Dashboard
    - Bike Build List export button with status filter
    - Family Contact List export button with status filter
    - Trigger browser download of generated CSV
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
    - _Agent Skills: `vue-best-practices`_

- [x] 17. Checkpoint — Frontend core features
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. Backend — Document Processing Pipeline (Textract + Bedrock)
  - [x] 18.1 Implement `process_document` Lambda — Textract OCR stage
    - Triggered by S3 event on uploads prefix
    - Call Textract AnalyzeDocument for OCR and form field extraction
    - Handle multi-page documents by combining extracted data from all pages into a single application record
    - Detect language automatically (English/Spanish) without manual selection
    - Extract circle-one selections (gender, preferred contact method, yes/no fields) by detecting circled/marked options
    - Extract Referring_Agency_Info fields and map to application record
    - _Requirements: 3.1, 3.2, 3.8, 3.9, 3.14, 3.15_
    - _Agent Skills: `lambda`, `s3`, `aws-serverless-eda`_

  - [x] 18.2 Implement `process_document` Lambda — Bedrock interpretation stage
    - Pass Textract results to Bedrock for interpretation of messy handwriting, multilingual content, and ambiguous values
    - Compute per-field confidence score by combining Textract and Bedrock confidence
    - Compute overall application confidence as minimum of all per-field scores
    - Flag low-confidence fields (below configurable threshold)
    - Set application status: "needs_review" if below threshold, "auto_approved" if at or above
    - Handle extraction failures: mark as "extraction_failed" and log error details
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4_
    - _Agent Skills: `lambda`, `bedrock`, `dynamodb`_

  - [x] 18.3 Implement Dream Bike Drawing extraction and analysis
    - Detect Dream Bike Drawing region in uploaded document
    - Crop drawing area and store as Drawing_Image in S3
    - Pass Drawing_Image to Bedrock to generate Drawing_Keywords (colors, bike style, accessories)
    - Extract "My dream bike is..." handwritten text and store as Dream_Bike_Description
    - Store Drawing_Keywords array and Dream_Bike_Description in child record
    - _Requirements: 3.10, 3.11, 3.12, 3.13, 10.2, 10.3, 10.7_
    - _Agent Skills: `lambda`, `bedrock`, `s3`_

  - [x] 18.4 Write unit tests for processing pipeline
    - Test Textract result parsing
    - Test confidence score computation (per-field and overall)
    - Test status assignment based on confidence threshold
    - Test extraction failure handling
    - Test Drawing_Keywords generation
    - _Requirements: 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4_
    - _Agent Skills: `lambda`, `bedrock`_

- [x] 19. Backend — Confidence threshold configuration Lambda
  - [x] 19.1 Implement confidence threshold read/update in Config table
    - Add endpoint to read and update the confidence threshold from the Config DynamoDB table
    - Default value: 0.80
    - _Requirements: 4.5_
    - _Agent Skills: `lambda`, `dynamodb`, `api-gateway`_

- [x] 20. Backend — Reports and Saved Reports Lambda functions (Python)
  - [x] 20.1 Implement `run_report` Lambda
    - Accept report configuration: selected columns, multiple filters with field-type-appropriate operators (equals, contains, greater than, less than, between, in list), group-by column, sort column and order
    - Compute summary statistics: total applications, total children, applications by status, applications by source type
    - Enforce giveaway year scoping for reporter role
    - Support pagination (default 50 rows, configurable page size)
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.7, 11.13, 11.14, 14.6_
    - _Agent Skills: `lambda`, `dynamodb`, `api-gateway`_

  - [x] 20.2 Implement `manage_reports` Lambda (CRUD for Saved Reports)
    - Save report configuration with user-defined name
    - List saved reports for current user
    - Load saved report (restore columns, filters, groupings, sort order)
    - Delete saved report
    - _Requirements: 11.8, 11.9, 11.10_
    - _Agent Skills: `lambda`, `dynamodb`_

  - [x] 20.3 Implement report CSV export endpoint
    - Export current report view as CSV with visible columns and applied filters
    - Record audit log entry for export action
    - _Requirements: 11.11, 15.5_
    - _Agent Skills: `lambda`, `dynamodb`_

  - [x] 20.4 Write unit tests for report Lambdas
    - Test filter operators
    - Test grouping and aggregation
    - Test pagination
    - Test saved report CRUD
    - _Requirements: 11.2, 11.3, 11.4, 11.8, 11.14_
    - _Agent Skills: `lambda`, `dynamodb`_

- [x] 21. Frontend — Reports section
  - [x] 21.1 Implement Reports UI with custom report builder
    - Column picker from all application fields
    - Multi-filter builder with field-type-appropriate operators
    - Group-by selector with aggregate counts
    - Sort by any column (ascending/descending)
    - Summary statistics bar (total applications, total children, by status, by source type)
    - Real-time result updates as filters/groupings change (no page reload)
    - Pagination with configurable page size
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.7, 11.13, 11.14_
    - _Agent Skills: `vue-best-practices`_

  - [x] 21.2 Implement charts, saved reports, and pre-built templates
    - Bar chart and pie chart for grouped data
    - Save/load/edit/delete saved report configurations
    - Pre-built templates: Height Distribution, Applications by Referring Agency, Applications by Zip Code, Age Distribution, Color Preferences, Language Distribution, Transportation Access Summary, Review Status Summary
    - CSV export of current report view
    - Giveaway_Year as filterable and groupable dimension for cross-year comparison
    - _Requirements: 11.6, 11.8, 11.9, 11.10, 11.11, 11.12, 17.5_
    - _Agent Skills: `vue-best-practices`_

  - [x] 21.3 Write unit tests for Reports UI
    - Test filter builder
    - Test chart rendering
    - Test saved report load/save
    - Test pre-built template loading
    - _Requirements: 11.6, 11.8, 11.10, 11.12_
    - _Agent Skills: `vue-testing-best-practices`_

- [x] 22. Backend — Cost Dashboard Lambda (Python)
  - [x] 22.1 Implement `get_cost_data` Lambda
    - Fetch cost data from AWS Cost Explorer API broken down by service (S3, CloudFront, Lambda, API Gateway, DynamoDB, Textract, Bedrock)
    - Return month-over-month trend for previous 6 months
    - Compute applications processed in current month and average cost per application
    - Cache cost data in Config DynamoDB table; refresh at most once per day
    - _Requirements: 13.2, 13.3, 13.4, 13.7, 13.8_
    - _Agent Skills: `lambda`, `aws-cost-operations`, `dynamodb`_

  - [x] 22.2 Implement budget threshold read/update endpoint
    - Read and update monthly cost budget threshold from Config table
    - _Requirements: 13.5_
    - _Agent Skills: `lambda`, `dynamodb`, `api-gateway`_

  - [x] 22.3 Write unit tests for cost dashboard Lambda
    - Test cost data caching (refresh at most once per day)
    - Test budget threshold comparison
    - _Requirements: 13.7, 13.8_
    - _Agent Skills: `lambda`, `aws-cost-operations`_

- [x] 23. Frontend — Cost Dashboard UI
  - [x] 23.1 Implement Cost Dashboard component
    - Service-level cost breakdown display
    - 6-month trend chart (month-over-month)
    - Applications processed count and cost-per-application
    - Budget threshold setting input
    - Prominent warning alert when estimated cost exceeds budget
    - Accessible from main admin navigation
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_
    - _Agent Skills: `vue-best-practices`_

- [x] 24. Backend — Access Management Lambda functions (Python)
  - [x] 24.1 Implement `manage_users` Lambda
    - Create user: create in Cognito User Pool + DynamoDB Users table, assign role
    - Update user: update role, authorized giveaway years (for reporters)
    - Deactivate user: disable in Cognito + set status inactive in DynamoDB; immediately reject subsequent requests
    - Enable user: re-enable in Cognito + set status active in DynamoDB
    - Delete user: remove from Cognito + DynamoDB
    - List users: name, email, role, authorized giveaway years, status, last login
    - Trigger password reset via Cognito for username/password accounts
    - Record audit log entries for all user management actions
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.7, 14.8, 14.9, 15.1_
    - _Agent Skills: `lambda`, `cognito`, `dynamodb`_

  - [x] 24.2 Write unit tests for access management Lambda
    - Test user CRUD operations
    - Test role assignment and giveaway year scoping for reporters
    - Test deactivation immediately rejects requests
    - _Requirements: 14.2, 14.5, 14.8_
    - _Agent Skills: `lambda`, `cognito`, `dynamodb`_

- [x] 25. Frontend — Access Management UI
  - [x] 25.1 Implement Access Management component
    - User list table: name, email, role, authorized giveaway years, status, last login
    - Create user form (linked to Cognito)
    - Edit user: role assignment, giveaway year selection for reporters
    - Deactivate/enable/delete user actions
    - Password reset trigger for username/password accounts
    - Accessible only to admin role
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.7, 14.8, 14.9_
    - _Agent Skills: `vue-best-practices`_

- [x] 26. Backend — Audit Log Lambda (Python)
  - [x] 26.1 Implement `get_audit_log` Lambda
    - Query audit log entries in reverse chronological order
    - Support filters: user, action type, resource type, date range
    - Support CSV export of filtered entries
    - _Requirements: 15.6, 15.7, 15.8, 15.9_
    - _Agent Skills: `lambda`, `dynamodb`_

  - [x] 26.2 Write unit tests for audit log Lambda
    - Test filtering by user, action type, resource type, date range
    - Test CSV export format
    - _Requirements: 15.7, 15.8, 15.9_
    - _Agent Skills: `lambda`, `dynamodb`_

- [x] 27. Frontend — Audit Log UI
  - [x] 27.1 Implement Audit Log Viewer component
    - Reverse-chronological table: timestamp, user name, action type, resource type, resource ID
    - Filters: user, action type, resource type, date range
    - CSV export of filtered entries
    - Accessible only to admin role
    - _Requirements: 15.6, 15.7, 15.8, 15.9_
    - _Agent Skills: `vue-best-practices`_

- [x] 28. Backend — Giveaway Year Lifecycle Lambda (Python)
  - [x] 28.1 Implement `manage_giveaway_year` Lambda
    - List giveaway years
    - Set active giveaway year in Config table
    - Archive year: mark all application records as read-only, move uploaded documents to S3 Glacier
    - Delete year: require confirmation, permanently remove all DynamoDB records and S3 objects (including archived), record action in audit log
    - _Requirements: 17.1, 17.2, 17.6, 17.7, 17.8, 17.9, 17.10, 17.11_
    - _Agent Skills: `lambda`, `dynamodb`, `s3`_

  - [x] 28.2 Write unit tests for giveaway year Lambda
    - Test archive marks records read-only and transitions S3 to Glacier
    - Test delete removes all DynamoDB records and S3 objects
    - Test audit log recording for delete action
    - _Requirements: 17.7, 17.8, 17.9, 17.10, 17.11_
    - _Agent Skills: `lambda`, `dynamodb`, `s3`_

- [x] 29. Frontend — Giveaway Year Management UI
  - [x] 29.1 Implement Giveaway Year Management component
    - List giveaway years with active indicator
    - Set active year control
    - Archive year action
    - Delete year action with confirmation dialog
    - Switch between years for historical data viewing
    - _Requirements: 17.2, 17.3, 17.4, 17.6, 17.9, 17.10_
    - _Agent Skills: `vue-best-practices`_

- [x] 30. Checkpoint — All admin features
  - Ensure all tests pass, ask the user if questions arise.

- [x] 31. CI/CD — GitHub Actions pipelines
  - [x] 31.1 Create backend deployment pipeline
    - GitHub Actions workflow triggered on pushes to main branch (backend paths)
    - Install Python dependencies, run linting (flake8/ruff), run pytest test suite
    - Halt on any lint or test failure — do NOT deploy
    - On success: package and deploy all Lambda functions, apply API Gateway and DynamoDB changes via CDK
    - Use OIDC federation to assume CI/CD IAM role (no long-lived access keys)
    - Output deployment summary as GitHub Actions job summary
    - Target: complete within 10 minutes
    - _Requirements: 12.1, 12.2, 12.3, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10_
    - _Agent Skills: `aws-cdk-development`, `iam`, `lambda`_

  - [x] 31.2 Create frontend deployment pipeline
    - GitHub Actions workflow triggered on pushes to main branch (frontend paths)
    - Install Node dependencies, run linting (ESLint), run Vitest test suite
    - Halt on any lint or test failure — do NOT deploy
    - On success: build Vue.js app, deploy static assets to S3, invalidate CloudFront cache
    - Use OIDC federation to assume CI/CD IAM role
    - Output deployment summary with CloudFront distribution URL
    - Target: complete within 10 minutes
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.8, 12.9, 12.10_
    - _Agent Skills: `aws-cdk-development`, `iam`, `s3`_

  - [x] 31.3 Write tests to validate pipeline configuration
    - Test that OIDC federation is configured correctly
    - Test that deployment halts on lint/test failure
    - _Requirements: 12.3, 12.8_
    - _Agent Skills: `iam`_

- [x] 32. Security hardening and final validation
  - [x] 32.1 Verify all encryption and security controls
    - Confirm DynamoDB encryption at rest (AES-256) on all tables
    - Confirm S3 SSE on all buckets
    - Confirm CloudFront HTTPS-only and TLS 1.2+
    - Confirm S3 Block Public Access on documents bucket
    - Confirm all Lambda IAM roles have no wildcard resource permissions
    - Confirm API Gateway requires Cognito JWT on all non-public endpoints
    - Confirm rate limiting on public endpoints
    - Confirm pre-signed URLs expire within 15 minutes
    - Confirm no PII in error responses or CloudWatch Logs
    - Confirm session timeout at 30 minutes
    - Confirm CI/CD IAM role has no data-read permissions
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12, 16.13_
    - _Agent Skills: `iam`, `s3`, `dynamodb`, `api-gateway`, `cognito`, `lambda`, `cloudwatch`_

  - [x] 32.2 Write integration tests for security controls
    - Test unauthenticated requests to protected endpoints return 401
    - Test unauthorized role access returns 403
    - Test reporter year scoping returns only authorized data
    - Test deactivated user requests are rejected
    - _Requirements: 14.6, 14.8, 14.10, 16.7_
    - _Agent Skills: `api-gateway`, `cognito`, `lambda`_

- [x] 33. Final checkpoint — Full system validation
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- **Codenames for open-source repo**: All frontend UI text uses "Greenfield Foundation" (for the organization) and "Community Gift Program" (for the event). Backend resource names (`bbp-hkbg-*`) are unchanged. This avoids public association during development.
- Each task references specific requirement clauses for traceability
- All 17 requirements are covered across the task list
- Data security (Requirement 16) is enforced throughout — in CDK stacks, backend middleware, and a dedicated hardening task
- Backend uses Python; frontend uses Vue.js with TypeScript; infrastructure uses CDK in TypeScript
- Separate CI/CD pipelines for backend and frontend as requested
- Auth bypass (`AUTH_ENABLED=false`) is implemented early (Task 6) so developers can work without Cognito locally
