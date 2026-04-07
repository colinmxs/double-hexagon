# Requirements Document

## Introduction

The Boise Bicycle Project (BBP) runs an annual Holiday Kids Bike Giveaway (HKBG) each December, receiving approximately 800 applications from dozens of community partners who identify families in need. Applications arrive in mixed formats: paper copies, scanned PDFs, and cell phone photos (PNG/JPEG). The current process of manually standardizing and extracting data from these applications to produce bike build lists and family contact lists is extremely time-intensive.

This system provides a web-based application that enables community partners to submit applications digitally or upload photos/scans of paper forms, automatically extracts structured data using OCR and AI, and gives BBP staff an admin dashboard to review, correct, and export the data. The solution must remain affordable for a nonprofit and must not create barriers for community partners who face limited tech access or language barriers.

**The protection and security of application data is the NUMBER ONE priority of this system.** The system stores personally identifiable information (PII) of minors, including names, addresses, and contact details. All security decisions must err on the side of caution, with least-privilege access fully enforced, all data encrypted at rest and in transit, and access tightly controlled and audited.

The system must also function season after season, with each giveaway year's data logically separated and independently manageable (archivable or deletable).

## Glossary

- **HKBG**: Holiday Kids Bike Giveaway, the annual December event run by BBP
- **BBP**: Boise Bicycle Project, the nonprofit organization operating the giveaway
- **Community_Partner**: An organization (Referring Agency) or individual who identifies families in need and submits HKBG applications on their behalf
- **Referring_Agency_Info**: The section of the application capturing the agency name, contact name, contact phone, and contact email of the Community Partner submitting the application
- **Application**: A completed HKBG registration form containing referring agency information, parent/guardian information, child details, bike color preferences, and a dream bike drawing page
- **Preferred_Contact_Method**: The parent/guardian's chosen communication channel: WhatsApp, Phone Call, Text Message, or Email
- **Dream_Bike_Description**: The child's written response to "My dream bike is..." on the Dream Bike Drawing page
- **Bike_Number**: An identifier assigned by BBP staff to a completed bike, recorded on the application after the giveaway event
- **Digital_Form**: The web-based version of the HKBG application form hosted on S3 with CloudFront
- **Upload_Portal**: The web interface where Community Partners submit photos or scans of paper applications
- **Processing_Pipeline**: The automated workflow that extracts structured data from uploaded documents using Textract and Bedrock
- **Extraction_Result**: The structured data output produced by the Processing Pipeline from a single uploaded document
- **Confidence_Score**: A numeric value (0.0 to 1.0) indicating the reliability of an extraction. Stored at two levels: per-field (on every individual extracted input value) and per-application (the minimum of all per-field scores in the application)
- **Admin_Dashboard**: The web interface used by BBP staff to review, correct, and export application data
- **Bike_Build_List**: A CSV export containing child names, heights, ages, color preferences, dream bike descriptions, and Drawing_Keywords used by volunteers to assemble bikes
- **Family_Contact_List**: A CSV export containing family names, phone numbers, email addresses, preferred contact methods, and addresses used for event coordination
- **Low_Confidence_Field**: An extracted field with a Confidence Score below a configurable threshold (default 0.80)
- **Static_Site**: The frontend web application hosted on S3 and served via CloudFront
- **REST_API**: The API Gateway endpoints that connect the Static Site to backend Lambda functions
- **DynamoDB_Table**: The database table storing structured application records
- **Textract**: The AWS service used for OCR and form field extraction from uploaded documents
- **Bedrock**: The AWS AI service used to interpret messy handwriting, handle multilingual content, and resolve ambiguous extractions
- **Cognito_User_Pool**: The Amazon Cognito User Pool that handles all user authentication, supporting both native username/password sign-in and Google (Gmail) federation. The system delegates all credential management to Cognito — no passwords are stored in the application database.
- **Dream_Bike_Drawing**: A child's hand-drawn illustration of their desired bike included on the HKBG application form
- **Drawing_Keywords**: Descriptive tags extracted from a Dream Bike Drawing by Bedrock, such as colors, accessories, and style attributes
- **Drawing_Image**: The cropped image of the Dream Bike Drawing region extracted from an uploaded document and stored in S3
- **Report**: A dynamic, filterable view of application data in the Admin Dashboard that supports grouping, aggregation, and visualization
- **Report_Filter**: A user-defined condition applied to narrow report data by any application field (e.g., bike size, Community Partner, status, age range)
- **Saved_Report**: A named Report configuration with specific filters, groupings, and columns that can be reloaded by BBP staff
- **CI_CD_Pipeline**: The GitHub Actions workflow that automatically builds, tests, and deploys code changes to the AWS environment on pushes to the main branch
- **OIDC_Federation**: OpenID Connect identity federation used by GitHub Actions to assume an AWS IAM role for deployment without storing long-lived credentials
- **Cost_Dashboard**: A section of the Admin Dashboard displaying estimated and actual AWS service costs for the current billing period
- **Access_Management**: The Admin Dashboard functionality for managing user accounts, roles, and permissions for BBP staff
- **Audit_Log**: A time-stamped record of every user action on the platform, including who performed the action, what action was taken, which resource was affected, and when it occurred
- **Giveaway_Year**: The calendar year associated with a specific HKBG event cycle (e.g., "2025" for the December 2025 giveaway). Every application and its associated data is tagged with a Giveaway Year.
- **Season_Archive**: The process of moving a completed Giveaway Year's data to cold storage, making it read-only and no longer visible in the active dashboard by default
- **PII**: Personally Identifiable Information, including names, addresses, phone numbers, and email addresses of families and minors

## Requirements

### Requirement 1: Digital Application Form

**User Story:** As a Community Partner, I want to fill out the HKBG application on a phone or computer, so that I can submit applications without printing or scanning paper forms.

#### Acceptance Criteria

1. THE Digital_Form SHALL present all fields matching the HKBG registration form organized into three sections: Referring Agency Information (agency name, contact name, contact phone, contact email), Parent/Guardian Information (first name, last name, address, city, zip code, phone, email, primary language spoken, English speaker in household yes/no, preferred contact method selection of WhatsApp/Phone Call/Text Message/Email, transportation access to giveaway event yes/no), and Child Information (first name, last name, accurate height in inches, age, gender selection of Male/Female/Non-binary, bike color 1, bike color 2, knows how to ride a bike yes/no, other siblings enrolled).
2. THE Digital_Form SHALL support entry of multiple children per family within a single application submission, each with their own Child Information section and Dream Bike Drawing page.
3. WHEN a Community Partner submits the Digital_Form, THE Digital_Form SHALL validate that all required fields contain values before submission, with child height in inches being a mandatory field.
4. WHEN a Community Partner submits a valid Digital_Form, THE REST_API SHALL store the application data directly in the DynamoDB_Table with a Confidence_Score of 1.0 for all fields.
5. THE Digital_Form SHALL render correctly on mobile devices with screen widths as small as 320 pixels.
6. THE Digital_Form SHALL provide both English and Spanish language versions, selectable by the Community Partner.
7. WHEN a Community Partner selects a language, THE Digital_Form SHALL display all labels, instructions, and validation messages in the selected language.
8. THE Digital_Form SHALL provide a drawing upload area where a Community Partner can upload a photo or image of the child's Dream Bike Drawing (PNG, JPEG) for each child entry.
9. WHEN a Dream Bike Drawing image is uploaded via the Digital_Form, THE REST_API SHALL store the Drawing_Image in S3 and link it to the corresponding child record in the DynamoDB_Table.
10. THE Digital_Form SHALL provide a text area for each child to enter their Dream_Bike_Description ("My dream bike is...").
11. THE Digital_Form SHALL display the note "*BBP does not provide training wheels. We teach the balance/strider method." in the Child Information section.

### Requirement 2: Document Upload Portal

**User Story:** As a Community Partner, I want to upload photos or scans of paper applications, so that I can submit applications without needing to re-enter data digitally.

#### Acceptance Criteria

1. THE Upload_Portal SHALL accept files in PDF, PNG, and JPEG formats.
2. THE Upload_Portal SHALL accept files up to 10 MB in size per upload.
3. WHEN a Community Partner uploads a file, THE Upload_Portal SHALL generate a pre-signed S3 URL and upload the file directly to the S3 bucket.
4. WHEN a file upload completes, THE Upload_Portal SHALL display a confirmation message with a reference identifier for the submission.
5. THE Upload_Portal SHALL allow a Community Partner to upload multiple files in a single session to support multi-page applications.
6. THE Upload_Portal SHALL provide instructions in both English and Spanish.
7. IF a Community Partner uploads a file that exceeds 10 MB or is not a supported format, THEN THE Upload_Portal SHALL display an error message specifying the file size limit and accepted formats.

### Requirement 3: Automated Document Processing Pipeline

**User Story:** As a BBP staff member, I want uploaded documents to be automatically processed and converted into structured data, so that I do not have to manually transcribe 800 applications.

#### Acceptance Criteria

1. WHEN a file is uploaded to the S3 bucket, THE Processing_Pipeline SHALL invoke a Lambda function to begin extraction.
2. THE Processing_Pipeline SHALL use Textract to perform OCR and form field extraction on the uploaded document.
3. WHEN Textract returns extraction results, THE Processing_Pipeline SHALL pass the results to Bedrock for interpretation of messy handwriting, multilingual content, and ambiguous field values.
4. WHEN Bedrock completes interpretation, THE Processing_Pipeline SHALL store the Extraction_Result as a structured record in the DynamoDB_Table.
5. THE Processing_Pipeline SHALL assign a Confidence_Score between 0.0 and 1.0 to each extracted field based on the combined confidence from Textract and Bedrock.
6. WHEN an extracted field has a Confidence_Score below the configurable threshold, THE Processing_Pipeline SHALL flag that field as a Low_Confidence_Field in the DynamoDB_Table record.
7. IF the Processing_Pipeline fails to extract data from a document, THEN THE Processing_Pipeline SHALL mark the application record as "extraction_failed" in the DynamoDB_Table and log the error details.
8. THE Processing_Pipeline SHALL process documents in English and Spanish without requiring the language to be specified in advance.
9. WHEN a multi-page document is uploaded, THE Processing_Pipeline SHALL combine extracted data from all pages into a single application record.
10. WHEN the Processing_Pipeline encounters a Dream Bike Drawing region in an uploaded document, THE Processing_Pipeline SHALL crop the drawing area and store it as a Drawing_Image in S3 linked to the child record.
11. THE Processing_Pipeline SHALL pass each Drawing_Image to Bedrock to generate Drawing_Keywords describing the drawing, including primary colors, bike style, and any accessories or features depicted.
12. THE Processing_Pipeline SHALL store the Drawing_Keywords as an array of strings in the child record in the DynamoDB_Table.
13. THE Processing_Pipeline SHALL extract the "My dream bike is..." written description from the Dream Bike Drawing page and store it as the Dream_Bike_Description in the child record.
14. THE Processing_Pipeline SHALL extract the Referring_Agency_Info fields (agency name, contact name, contact phone, contact email) and map them to the application record.
15. THE Processing_Pipeline SHALL extract circle-one selections (gender, preferred contact method, English speaker yes/no, transportation access yes/no, knows how to ride yes/no) by detecting circled or marked options in the uploaded document.

### Requirement 4: Confidence Scoring and Human Review Flagging

**User Story:** As a BBP staff member, I want extracted data to include confidence scores and automatic flagging of uncertain results, so that I can focus my review time on applications that need human attention.

#### Acceptance Criteria

1. THE Processing_Pipeline SHALL compute a Confidence_Score for each extracted field by combining the Textract confidence value with the Bedrock interpretation confidence.
2. THE Processing_Pipeline SHALL compute an overall application Confidence_Score as the minimum Confidence_Score across all fields in the application.
3. WHEN an application has an overall Confidence_Score below the configurable threshold, THE Processing_Pipeline SHALL set the application status to "needs_review" in the DynamoDB_Table.
4. WHEN an application has an overall Confidence_Score at or above the configurable threshold, THE Processing_Pipeline SHALL set the application status to "auto_approved" in the DynamoDB_Table.
5. THE Admin_Dashboard SHALL allow BBP staff to configure the Confidence_Score threshold, with a default value of 0.80.

### Requirement 5: Admin Dashboard - Application Review

**User Story:** As a BBP staff member, I want to view, search, and correct application data in a dashboard, so that I can efficiently review and finalize all applications before the giveaway event.

#### Acceptance Criteria

1. THE Admin_Dashboard SHALL display a list of all applications with columns for family name, submission date, source (digital form or upload), status (needs_review, auto_approved, manually_approved), and overall Confidence_Score.
2. THE Admin_Dashboard SHALL allow BBP staff to filter applications by status.
3. THE Admin_Dashboard SHALL allow BBP staff to search applications by family name or Community Partner name.
4. WHEN a BBP staff member selects an uploaded application, THE Admin_Dashboard SHALL present a side-by-side review view with the original uploaded document(s)/image(s) displayed on one side and an editable form containing the transcription results on the other side, allowing the reviewer to visually compare each extracted value against the source document.
5. THE side-by-side review view SHALL support multi-page documents by allowing the reviewer to navigate between pages of the original document while the transcription form remains visible and scrollable.
6. THE side-by-side review view SHALL display the per-field Confidence_Score next to each transcribed value, so the reviewer can see exactly how confident the extraction was for every individual input.
7. WHEN a BBP staff member edits an extracted field value, THE Admin_Dashboard SHALL save the corrected value to the DynamoDB_Table and set that field's Confidence_Score to 1.0.
6. WHEN a BBP staff member approves an application, THE Admin_Dashboard SHALL update the application status to "manually_approved" in the DynamoDB_Table.
7. THE Admin_Dashboard SHALL display Low_Confidence_Fields with a visual indicator distinguishing them from high-confidence fields.
8. WHEN a BBP staff member views a child record, THE Admin_Dashboard SHALL display the Drawing_Image and its associated Drawing_Keywords.
9. THE Admin_Dashboard SHALL allow BBP staff to edit Drawing_Keywords for any child record.
10. THE Admin_Dashboard SHALL allow BBP staff to assign a Bike_Number to each child record, representing the physical bike built for that child.

### Requirement 6: Data Export

**User Story:** As a BBP staff member, I want to export bike build lists and family contact lists as CSV files, so that I can distribute them to volunteers and coordinators for the giveaway event.

#### Acceptance Criteria

1. WHEN a BBP staff member requests a Bike_Build_List export, THE Admin_Dashboard SHALL generate a CSV file containing child first name, child last name, height in inches, age, gender, bike color 1, bike color 2, knows how to ride, Dream_Bike_Description, Drawing_Keywords, and Bike_Number for each child across all approved applications.
2. WHEN a BBP staff member requests a Family_Contact_List export, THE Admin_Dashboard SHALL generate a CSV file containing parent/guardian first name, last name, phone, email, address, city, zip code, primary language spoken, Preferred_Contact_Method, transportation access, and referring agency name for each approved application.
3. THE Admin_Dashboard SHALL allow BBP staff to select which applications to include in an export by status filter.
4. WHEN a BBP staff member initiates an export, THE Admin_Dashboard SHALL generate the CSV file and trigger a browser download.
5. THE Admin_Dashboard SHALL include a header row in all exported CSV files with descriptive column names.

### Requirement 7: Multilingual Support

**User Story:** As a Community Partner with limited English proficiency, I want to use the application system in Spanish, so that I can submit applications without language being a barrier.

#### Acceptance Criteria

1. THE Static_Site SHALL detect the browser language preference and default to the matching supported language (English or Spanish).
2. THE Static_Site SHALL provide a language toggle visible on all pages allowing the user to switch between English and Spanish.
3. WHEN a Community Partner switches languages, THE Static_Site SHALL update all interface text without requiring a page reload.
4. THE Digital_Form SHALL accept input in any language regardless of the selected interface language.
5. THE Processing_Pipeline SHALL detect the language of handwritten or printed text in uploaded documents and process extraction accordingly without manual language selection.

### Requirement 8: Static Site Hosting and Infrastructure

**User Story:** As a BBP staff member, I want the system hosted affordably on AWS, so that the nonprofit can sustain the solution without significant ongoing costs.

#### Acceptance Criteria

1. THE Static_Site SHALL be hosted on S3 and served through CloudFront.
2. THE REST_API SHALL be implemented using API Gateway connected to Lambda functions.
3. THE REST_API SHALL use a Cognito User Pool authorizer to authenticate and restrict Admin_Dashboard access to authorized BBP staff. The Cognito User Pool SHALL support both native username/password sign-in and Google (Gmail) as a federated identity provider. All credential storage and password management is handled by Cognito — the application database SHALL NOT store passwords or password hashes.
4. THE Static_Site SHALL load the initial page within 3 seconds on a standard mobile connection.
5. WHILE the system is not in active use (outside of the October-December application season), THE infrastructure SHALL incur minimal cost by relying on serverless pay-per-use pricing with no always-on compute resources.

### Requirement 9: Application Data Storage

**User Story:** As a BBP staff member, I want all application data stored reliably, so that no applications are lost during the processing and review cycle.

#### Acceptance Criteria

1. THE DynamoDB_Table SHALL store each application record with: a unique application identifier, Giveaway_Year, submission timestamp, source type (digital or upload), Referring_Agency_Info (agency name, contact name, contact phone, contact email), Parent/Guardian information (first name, last name, address, city, zip code, phone, email, primary language spoken, English speaker in household, Preferred_Contact_Method, transportation access), child information array where each child contains (first name, last name, height in inches, age, gender, bike color 1, bike color 2, knows how to ride, other siblings enrolled, Drawing_Image S3 key, Drawing_Keywords, Dream_Bike_Description, Bike_Number), an overall application Confidence_Score, and application status.
2. THE DynamoDB_Table SHALL store a per-field Confidence_Score (0.0 to 1.0) for every individual extracted input value in the application record, stored as a parallel map keyed by field name so that each value has its own associated confidence.
2. WHEN an application record is created or updated, THE DynamoDB_Table SHALL retain the previous version of the record for audit purposes.
3. THE S3 bucket SHALL retain all original uploaded documents for the duration of the giveaway cycle.
4. IF a DynamoDB write operation fails, THEN THE REST_API SHALL return an error response to the client and log the failure details.

### Requirement 10: Dream Bike Drawing Capture

**User Story:** As a BBP staff member, I want each child's dream bike drawing and written description captured and described with keywords, so that volunteers can reference the drawing and its details when building bikes.

#### Acceptance Criteria

1. WHEN a Community Partner submits a Digital_Form with a Drawing_Image, THE REST_API SHALL store the image in S3 and associate it with the child record.
2. WHEN the Processing_Pipeline extracts a Dream Bike Drawing from an uploaded document, THE Processing_Pipeline SHALL use Bedrock to identify the drawing region, crop it, and store the Drawing_Image in S3.
3. THE Processing_Pipeline SHALL use Bedrock to analyze each Drawing_Image and generate Drawing_Keywords including: primary color(s), secondary color(s), bike style (e.g., mountain, BMX, cruiser, road), and depicted accessories (e.g., basket, streamers, bell, water bottle).
4. THE Admin_Dashboard SHALL display the Drawing_Image as a thumbnail in the application list view and as a full-size image in the detail view.
5. THE Bike_Build_List export SHALL include Drawing_Keywords and Dream_Bike_Description columns for each child.
6. THE Admin_Dashboard SHALL allow BBP staff to add, remove, or edit Drawing_Keywords for any child record.
7. THE Processing_Pipeline SHALL extract the "My dream bike is..." handwritten text from the Dream Bike Drawing page and store it as the Dream_Bike_Description.
8. THE Admin_Dashboard SHALL display and allow editing of the Dream_Bike_Description alongside the Drawing_Image.

### Requirement 11: Reporting and Analytics

**User Story:** As a BBP staff member, I want a full-featured reporting experience that lets me slice and dice application data by any dimension, so that I can make informed decisions about bike inventory, volunteer assignments, and community partner engagement.

#### Acceptance Criteria

1. THE Admin_Dashboard SHALL provide a dedicated Reports section accessible from the main navigation.
2. THE Reports section SHALL allow BBP staff to build custom reports by selecting columns from any application field, including: referring agency name, parent/guardian name, address, city, zip code, primary language spoken, preferred contact method, transportation access, submission date, source type, application status, child name, child height in inches, child age, child gender, bike color 1, bike color 2, knows how to ride, Dream_Bike_Description, Drawing_Keywords, Bike_Number, and Confidence_Score.
3. THE Reports section SHALL allow BBP staff to apply multiple Report_Filters simultaneously, with each filter supporting operators appropriate to the field type (e.g., equals, contains, greater than, less than, between, in list).
4. THE Reports section SHALL allow BBP staff to group report rows by any selected column and display aggregate counts for each group.
5. THE Reports section SHALL display summary statistics at the top of each report, including: total applications, total children, applications by status breakdown, and applications by source type breakdown.
6. THE Reports section SHALL provide visual charts (bar chart and pie chart) for grouped data to support at-a-glance analysis.
7. THE Reports section SHALL allow BBP staff to sort report results by any column in ascending or descending order.
8. THE Reports section SHALL allow BBP staff to save a report configuration as a Saved_Report with a user-defined name.
9. THE Reports section SHALL display a list of Saved_Reports that BBP staff can load, edit, or delete.
10. WHEN a BBP staff member loads a Saved_Report, THE Reports section SHALL restore all previously configured columns, filters, groupings, and sort order.
11. THE Reports section SHALL allow BBP staff to export any report view as a CSV file with the currently visible columns and applied filters.
12. THE Reports section SHALL provide pre-built report templates for common use cases: "Height Distribution" (for bike sizing), "Applications by Referring Agency", "Applications by Zip Code", "Age Distribution", "Color Preferences", "Language Distribution", "Transportation Access Summary", and "Review Status Summary".
13. THE Reports section SHALL update report results in real-time as filters and groupings are changed, without requiring a page reload or explicit refresh action.
14. THE Reports section SHALL support pagination for reports with more than 50 rows, with configurable page size.

### Requirement 12: CI/CD Pipeline

**User Story:** As a developer, I want code changes automatically built, tested, and deployed to the AWS environment via GitHub Actions, so that I can ship updates quickly and reliably without manual deployment steps.

#### Acceptance Criteria

1. THE repository SHALL contain a GitHub Actions workflow that triggers on pushes to the main branch.
2. WHEN the workflow triggers, THE pipeline SHALL install dependencies, run linting, and execute the test suite before proceeding to deployment.
3. IF any lint or test step fails, THEN THE pipeline SHALL halt and NOT deploy to the environment.
4. WHEN all checks pass, THE pipeline SHALL deploy the Static_Site assets to the S3 bucket and invalidate the CloudFront distribution cache.
5. WHEN all checks pass, THE pipeline SHALL package and deploy all Lambda functions to AWS.
6. WHEN all checks pass, THE pipeline SHALL apply any API Gateway configuration changes.
7. WHEN all checks pass, THE pipeline SHALL apply any DynamoDB_Table schema or configuration changes.
8. THE pipeline SHALL use GitHub Actions OIDC federation with an AWS IAM role to authenticate, avoiding long-lived access keys.
9. THE pipeline SHALL complete a full build-and-deploy cycle within 10 minutes under normal conditions.
10. THE pipeline SHALL output a deployment summary as a GitHub Actions job summary, including deployed resource versions and the CloudFront distribution URL.

### Requirement 13: Cost Monitoring Dashboard

**User Story:** As a BBP administrator, I want to see how much the platform is costing in AWS charges, so that I can ensure the system stays within the nonprofit's budget and identify any unexpected cost spikes.

#### Acceptance Criteria

1. THE Admin_Dashboard SHALL provide a Cost_Dashboard section accessible from the main navigation.
2. THE Cost_Dashboard SHALL display the current month's estimated AWS costs broken down by service (S3, CloudFront, Lambda, API Gateway, DynamoDB, Textract, Bedrock).
3. THE Cost_Dashboard SHALL display a month-over-month cost trend chart showing the previous 6 months of costs.
4. THE Cost_Dashboard SHALL display the number of applications processed in the current month and the average cost per application.
5. THE Cost_Dashboard SHALL allow BBP staff to set a monthly cost budget threshold.
6. WHEN the estimated monthly cost exceeds the configured budget threshold, THE Cost_Dashboard SHALL display a prominent warning alert on the dashboard.
7. THE Cost_Dashboard SHALL retrieve cost data from the AWS Cost Explorer API via a Lambda function.
8. THE Cost_Dashboard SHALL refresh cost data at most once per day to minimize AWS Cost Explorer API charges.

### Requirement 14: Access Management

**User Story:** As a BBP administrator, I want to manage who has access to the admin platform and what they can do, so that I can control access to sensitive family data and ensure only authorized staff can make changes.

#### Acceptance Criteria

1. THE Admin_Dashboard SHALL provide an Access_Management section accessible only to users with the "admin" role.
2. THE Access_Management section SHALL allow administrators to create, edit, deactivate, and delete user accounts. User accounts are linked to Cognito identities (username/password or Google/Gmail federation); all credential management is delegated to Cognito.
3. THE Access_Management section SHALL support three roles:
   - **admin**: Full access to all platform features including access management, cost dashboard, audit logs, giveaway year lifecycle management, application review, reports, and exports.
   - **reporter**: Read-only access to the Reports section and Data Export, scoped to specific Giveaway Years assigned by an administrator. No access to application detail views, editing, access management, cost dashboard, or audit logs.
   - **submitter**: Access only to the Digital_Form and Upload_Portal to submit applications. No access to the Admin_Dashboard, reports, exports, or any other administrative features.
4. THE Access_Management section SHALL allow administrators to designate other users as "admin", granting them the same full access.
5. WHEN an administrator assigns the "reporter" role to a user, THE Access_Management section SHALL require the administrator to select one or more Giveaway Years that the reporter is authorized to access.
6. THE REST_API SHALL enforce Giveaway Year scoping for "reporter" users, returning only data from their authorized Giveaway Years on all report and export endpoints.
7. THE Access_Management section SHALL display a list of all user accounts with columns for name, email, role, authorized Giveaway Years (for reporters), status (active/inactive), and last login timestamp.
8. WHEN an administrator deactivates a user account, THE REST_API SHALL immediately reject any subsequent requests authenticated with that user's credentials.
9. THE Access_Management section SHALL allow administrators to trigger a password reset for a user via Cognito for users with native username/password accounts.
10. THE REST_API SHALL enforce role-based access control on all endpoints, returning a 403 response when a user attempts an action not permitted by their role.
11. THE "submitter" role SHALL NOT require access to the Admin_Dashboard; submitters interact only with the public-facing Digital_Form and Upload_Portal.

### Requirement 15: Audit Logging

**User Story:** As a BBP administrator, I want a complete audit trail of who accessed the platform, when, and what they did, so that I can ensure accountability and investigate any issues with data handling.

#### Acceptance Criteria

1. THE system SHALL record an Audit_Log entry for every authenticated user action, including: user identifier, timestamp, action type (view, create, update, delete, export, login, logout), resource type (application, child record, report, user account), and resource identifier.
2. WHEN a BBP staff member views an application detail page, THE system SHALL record an Audit_Log entry with action type "view" and the application identifier.
3. WHEN a BBP staff member updates any field on an application, THE system SHALL record an Audit_Log entry with action type "update", the application identifier, the field name, the previous value, and the new value.
4. WHEN a BBP staff member deletes an application, THE system SHALL record an Audit_Log entry with action type "delete" and the application identifier.
5. WHEN a BBP staff member exports data, THE system SHALL record an Audit_Log entry with action type "export", the export type (Bike_Build_List, Family_Contact_List, or report), and the filters applied.
6. THE Admin_Dashboard SHALL provide an Audit Log section accessible only to users with the administrator role.
7. THE Audit Log section SHALL display audit entries in reverse chronological order with columns for timestamp, user name, action type, resource type, and resource identifier.
8. THE Audit Log section SHALL allow administrators to filter audit entries by user, action type, resource type, and date range.
9. THE Audit Log section SHALL allow administrators to export filtered audit entries as a CSV file.
10. THE system SHALL store Audit_Log entries in a separate DynamoDB table with a retention period of at least 12 months.

### Requirement 16: Data Security and PII Protection

**User Story:** As a BBP administrator, I want all personally identifiable information — especially data belonging to minors — secured to the highest standard, so that families can trust their data is protected and the organization meets its duty of care.

#### Acceptance Criteria

1. ALL data stored in DynamoDB SHALL be encrypted at rest using AWS-managed encryption keys (AES-256).
2. ALL data stored in S3 (uploaded documents, Drawing Images, static site assets) SHALL be encrypted at rest using S3 server-side encryption (SSE-S3 or SSE-KMS).
3. ALL data in transit between the client and the REST_API SHALL be encrypted using TLS 1.2 or higher.
4. ALL data in transit between the Static_Site and CloudFront SHALL be served exclusively over HTTPS.
5. THE S3 buckets containing uploaded documents and application data SHALL have public access blocked at the bucket level via S3 Block Public Access settings.
6. ALL Lambda function execution roles SHALL follow the principle of least privilege, granting only the specific DynamoDB, S3, Textract, and Bedrock permissions required for that function's purpose.
7. THE API Gateway SHALL require a valid Cognito-issued JWT token on all endpoints except the public Digital_Form submission and Upload_Portal endpoints.
8. THE public Digital_Form submission and Upload_Portal endpoints SHALL be rate-limited to prevent abuse.
9. Pre-signed S3 URLs generated for file uploads SHALL expire within 15 minutes of generation.
10. THE REST_API SHALL NOT return raw PII data in error responses or log PII values in CloudWatch Logs.
11. THE Admin_Dashboard SHALL automatically log out inactive sessions after 30 minutes of inactivity.
12. ALL IAM roles and policies used by the system SHALL be scoped to the specific resources they need to access, with no wildcard resource permissions.
13. THE CI_CD_Pipeline IAM role SHALL be scoped to only the resources required for deployment, with no administrative or data-read permissions.

### Requirement 17: Giveaway Year Lifecycle Management

**User Story:** As a BBP administrator, I want each giveaway season's data kept separate and manageable across years, so that I can run the system season after season, archive old data, and keep the active dashboard focused on the current year.

#### Acceptance Criteria

1. EVERY application record SHALL be tagged with a Giveaway_Year value representing the year of the HKBG event (e.g., "2025").
2. THE Admin_Dashboard SHALL allow administrators to configure the active Giveaway_Year for the current season.
3. THE Admin_Dashboard SHALL default all views (application list, reports, exports) to show only data from the active Giveaway_Year.
4. THE Admin_Dashboard SHALL allow BBP staff to switch between Giveaway Years to view historical data when needed.
5. THE Reports section SHALL include Giveaway_Year as a filterable and groupable dimension, enabling cross-year comparison reports.
6. THE Admin_Dashboard SHALL provide a Season_Archive action that an administrator can invoke to archive a completed Giveaway Year's data.
7. WHEN an administrator archives a Giveaway Year, THE system SHALL mark all application records for that year as read-only, preventing any further edits.
8. WHEN an administrator archives a Giveaway Year, THE system SHALL move uploaded documents for that year to S3 Glacier or an equivalent low-cost storage class.
9. THE Admin_Dashboard SHALL provide a data deletion action that an administrator can invoke to permanently delete all application records, uploaded documents, and Drawing Images for a specified Giveaway Year.
10. WHEN an administrator initiates a Giveaway Year deletion, THE system SHALL require a confirmation step and record the action in the Audit_Log.
11. WHEN an administrator initiates a Giveaway Year deletion, THE system SHALL permanently remove all associated records from DynamoDB and all associated objects from S3, including archived objects.
12. THE Digital_Form and Upload_Portal SHALL automatically tag new submissions with the currently active Giveaway_Year.
