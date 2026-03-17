# Tech Stack & Build Commands

## Frontend
- **Framework**: Vue 3 (Composition API with `<script setup>` and TypeScript)
- **Build tool**: Vite 8
- **State management**: Pinia 3
- **Routing**: Vue Router 4
- **i18n**: vue-i18n 9 (English + Spanish, locale files in `frontend/src/locales/`)
- **Testing**: Vitest 4 + @vue/test-utils + happy-dom
- **Linting**: ESLint 10 + typescript-eslint + eslint-plugin-vue
- **Type checking**: vue-tsc

## Backend
- **Runtime**: Python 3.12
- **Lambda handlers**: One handler per function in `backend/lambdas/<function_name>/handler.py`
- **Entry point**: `handler(event, context)` function in each handler module
- **AWS services used**: DynamoDB, S3, Textract, Bedrock, Cognito, API Gateway

## Infrastructure
- **IaC**: AWS CDK (TypeScript) with `aws-cdk-lib` 2.243
- **Testing**: Jest + ts-jest
- **5 CDK stacks**: storage, auth, api, frontend, cicd

## Common Commands

All commands must be run inside the Docker container (see `docker-execution.md`).

```bash
# Frontend
cd frontend && npm run dev          # Dev server (localhost:5173)
cd frontend && npm run build        # Type-check + production build
cd frontend && npx vitest run       # Run tests (single pass)
cd frontend && npx eslint .         # Lint

# Infrastructure
cd infra && npm test                # Jest CDK tests
cd infra && npx cdk synth           # Synthesize CloudFormation
cd infra && npx cdk diff            # Preview changes
cd infra && npx cdk deploy --all    # Deploy all stacks

# Backend (Python)
python -m pytest backend/           # Run backend tests
```
