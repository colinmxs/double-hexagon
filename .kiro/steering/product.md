# Product Overview

BBP HKBG (Holiday Kids Bike Giveaway) is a web application for managing a charitable bike giveaway program. It supports two user-facing workflows:

1. **Public application intake** — Families apply for bikes via a digital form or by uploading paper forms (processed with AWS Textract + Bedrock OCR).
2. **Admin review & management** — Staff review applications, manage giveaway years, run reports, export data (bike build lists, family contact lists), track costs, and manage user access.

Key characteristics:
- Bilingual (English / Spanish) via vue-i18n
- Role-based access: `admin`, `reporter`, `submitter`
- Cognito authentication with Google federation
- Serverless AWS backend (Lambda, DynamoDB, S3, API Gateway)
- OCR pipeline for scanned paper applications using Textract and Bedrock
- Confidence scoring on OCR-extracted fields
