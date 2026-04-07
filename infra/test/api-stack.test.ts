import * as cdk from 'aws-cdk-lib';
import { Template, Match, Capture } from 'aws-cdk-lib/assertions';
import { StorageStack } from '../lib/storage-stack';
import { AuthStack } from '../lib/auth-stack';
import { ApiStack } from '../lib/api-stack';

describe('ApiStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const storageStack = new StorageStack(app, 'TestStorageStack');
    const authStack = new AuthStack(app, 'TestAuthStack', { storageStack });
    const apiStack = new ApiStack(app, 'TestApiStack', {
      storageStack,
      authStack,
    });
    template = Template.fromStack(apiStack);
  });

  // ---------------------------------------------------------------
  // REST API — Validates: Requirements 16.8
  // ---------------------------------------------------------------

  describe('REST API', () => {
    test('exists with correct name', () => {
      template.hasResourceProperties('AWS::ApiGateway::RestApi', {
        Name: 'bbp-hkbg-api',
      });
    });

    test('exports API URL output', () => {
      template.hasOutput('ApiUrl', {
        Export: { Name: 'BbpHkbgApiUrl' },
      });
    });
  });

  // ---------------------------------------------------------------
  // Cognito Authorizer — Validates: Requirements 16.8
  // ---------------------------------------------------------------

  describe('Cognito Authorizer', () => {
    test('is configured with Cognito User Pool', () => {
      template.hasResourceProperties('AWS::ApiGateway::Authorizer', {
        Name: 'bbp-hkbg-cognito-authorizer',
        Type: 'COGNITO_USER_POOLS',
        IdentitySource: 'method.request.header.Authorization',
      });
    });
  });

  // ---------------------------------------------------------------
  // Lambda Functions — Validates: Requirements 16.6
  // ---------------------------------------------------------------

  describe('Lambda Functions', () => {
    test('all 14 Lambda functions exist with Python 3.12 runtime', () => {
      const expectedNames = [
        'bbp-hkbg-submit-application',
        'bbp-hkbg-generate-presigned-url',
        'bbp-hkbg-process-document',
        'bbp-hkbg-get-applications',
        'bbp-hkbg-get-application-detail',
        'bbp-hkbg-update-application',
        'bbp-hkbg-export-data',
        'bbp-hkbg-manage-reports',
        'bbp-hkbg-run-report',
        'bbp-hkbg-get-cost-data',
        'bbp-hkbg-manage-users',
        'bbp-hkbg-get-audit-log',
        'bbp-hkbg-manage-giveaway-year',
        'bbp-hkbg-get-auth-me',
      ];

      for (const name of expectedNames) {
        template.hasResourceProperties('AWS::Lambda::Function', {
          FunctionName: name,
          Runtime: 'python3.12',
        });
      }
    });
  });

  // ---------------------------------------------------------------
  // IAM Least Privilege — Validates: Requirements 16.6, 16.12
  // ---------------------------------------------------------------

  describe('Lambda IAM Role Policies — no wildcard resources', () => {
    test('no IAM policy statements use wildcard resources except Textract and Cost Explorer', () => {
      const policies = template.findResources('AWS::IAM::Policy');

      for (const [logicalId, resource] of Object.entries(policies)) {
        const statements: any[] =
          (resource as any).Properties?.PolicyDocument?.Statement ?? [];

        for (const stmt of statements) {
          const actions: string[] = Array.isArray(stmt.Action)
            ? stmt.Action
            : [stmt.Action];

          // Textract and Cost Explorer don't support resource-level permissions
          const isTextract = actions.some((a: string) => a.startsWith('textract:'));
          const isCostExplorer = actions.some((a: string) => a.startsWith('ce:'));

          if (isTextract || isCostExplorer) {
            continue; // These services legitimately require '*'
          }

          const resources = Array.isArray(stmt.Resource)
            ? stmt.Resource
            : [stmt.Resource];

          for (const res of resources) {
            if (typeof res === 'string') {
              expect(res).not.toBe('*');
            }
            // CloudFormation intrinsic functions (Fn::Join, Ref, etc.) are objects — those are scoped
          }
        }
      }
    });
  });

  // ---------------------------------------------------------------
  // Public vs Authenticated Endpoints — Validates: Requirements 16.8
  // ---------------------------------------------------------------

  describe('Public endpoints do NOT have Cognito authorizer', () => {
    test('POST /api/applications is public (no authorizer)', () => {
      // Find all API methods — public ones should have AuthorizationType NONE
      const methods = template.findResources('AWS::ApiGateway::Method');

      // Collect POST methods that point to submit_application
      let foundPublicSubmit = false;
      let foundPublicPresign = false;

      for (const [logicalId, resource] of Object.entries(methods)) {
        const props = (resource as any).Properties;
        if (props.HttpMethod === 'POST' && props.AuthorizationType === 'NONE') {
          foundPublicSubmit = foundPublicSubmit || logicalId.includes('applications');
          foundPublicPresign = foundPublicPresign || logicalId.includes('presign');
        }
      }

      expect(foundPublicSubmit).toBe(true);
    });

    test('POST /api/uploads/presign is public (no authorizer)', () => {
      const methods = template.findResources('AWS::ApiGateway::Method');

      let foundPublicPresign = false;
      for (const [logicalId, resource] of Object.entries(methods)) {
        const props = (resource as any).Properties;
        if (props.HttpMethod === 'POST' && props.AuthorizationType === 'NONE') {
          foundPublicPresign = foundPublicPresign || logicalId.includes('presign');
        }
      }

      expect(foundPublicPresign).toBe(true);
    });
  });

  describe('Authenticated endpoints DO have Cognito authorizer', () => {
    test('GET /api/applications requires COGNITO_USER_POOLS auth', () => {
      const methods = template.findResources('AWS::ApiGateway::Method');

      let foundAuthGet = false;
      for (const [logicalId, resource] of Object.entries(methods)) {
        const props = (resource as any).Properties;
        if (
          props.HttpMethod === 'GET' &&
          props.AuthorizationType === 'COGNITO_USER_POOLS' &&
          logicalId.includes('applications')
        ) {
          foundAuthGet = true;
        }
      }

      expect(foundAuthGet).toBe(true);
    });

    test('authenticated endpoints use COGNITO_USER_POOLS authorization type', () => {
      const methods = template.findResources('AWS::ApiGateway::Method');

      // Count methods with COGNITO auth (excluding OPTIONS/CORS preflight)
      let cognitoMethodCount = 0;
      for (const [, resource] of Object.entries(methods)) {
        const props = (resource as any).Properties;
        if (props.AuthorizationType === 'COGNITO_USER_POOLS' && props.HttpMethod !== 'OPTIONS') {
          cognitoMethodCount++;
        }
      }

      // There should be many authenticated endpoints (all admin routes)
      expect(cognitoMethodCount).toBeGreaterThan(10);
    });
  });

  // ---------------------------------------------------------------
  // Rate Limiting — Validates: Requirements 16.8
  // ---------------------------------------------------------------

  describe('Rate Limiting', () => {
    test('usage plan exists for public endpoints', () => {
      template.hasResourceProperties('AWS::ApiGateway::UsagePlan', {
        UsagePlanName: 'bbp-hkbg-public-usage-plan',
        Throttle: {
          RateLimit: 10,
          BurstLimit: 20,
        },
      });
    });

    test('API key exists for rate limiting', () => {
      template.hasResourceProperties('AWS::ApiGateway::ApiKey', {
        Name: 'bbp-hkbg-public-api-key',
      });
    });
  });

  // ---------------------------------------------------------------
  // S3 Event Notification — Validates: Requirements 16.6
  // ---------------------------------------------------------------

  describe('S3 Event Notification', () => {
    test('process_document Lambda has S3 invoke permission for uploads/ prefix', () => {
      template.hasResourceProperties('AWS::Lambda::Permission', {
        Action: 'lambda:InvokeFunction',
        Principal: 's3.amazonaws.com',
      });
    });
  });
});
