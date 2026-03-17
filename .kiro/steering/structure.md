# Project Structure

```
├── backend/
│   └── lambdas/                    # One folder per Lambda function
│       └── <function_name>/
│           └── handler.py          # Entry point: handler(event, context)
│
├── frontend/                       # Vue 3 SPA
│   └── src/
│       ├── components/             # Reusable Vue components
│       │   └── __tests__/          # Component tests (*.spec.ts)
│       ├── composables/            # Vue composables (useAuth, useReports, etc.)
│       ├── views/                  # Route-level page components
│       │   └── __tests__/          # View tests (*.spec.ts)
│       ├── locales/                # i18n JSON files (en.json, es.json)
│       ├── router/                 # Vue Router config
│       ├── App.vue                 # Root component
│       ├── main.ts                 # App entry point
│       └── i18n.ts                 # i18n setup
│
├── infra/                          # AWS CDK (TypeScript)
│   ├── bin/                        # CDK app entry point
│   ├── lib/                        # Stack definitions
│   │   ├── storage-stack.ts        # S3 + DynamoDB
│   │   ├── auth-stack.ts           # Cognito
│   │   ├── api-stack.ts            # API Gateway + Lambdas
│   │   ├── frontend-stack.ts       # CloudFront + S3 hosting
│   │   └── cicd-stack.ts           # GitHub Actions OIDC
│   └── test/                       # CDK stack tests (*.test.ts)
│
├── docs/
│   └── INFRASTRUCTURE.md           # Deployment & architecture guide
│
└── .kiro/
    ├── specs/                      # Feature specs
    └── steering/                   # AI steering rules
```

## Conventions
- Frontend tests live alongside their source in `__tests__/` directories, named `*.spec.ts`
- Each Lambda is isolated in its own folder with a single `handler.py`
- CDK stacks are one-per-file in `infra/lib/`, composed in `infra/bin/infra.ts`
- Routes use lazy loading (`() => import(...)`) in the router
- Public routes: `/apply`, `/upload`
- Admin routes: `/admin/*` (auth-gated, role-checked via router guards)
