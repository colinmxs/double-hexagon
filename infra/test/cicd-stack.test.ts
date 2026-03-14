import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { CiCdStack } from '../lib/cicd-stack';

describe('CiCdStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const cicdStack = new CiCdStack(app, 'TestCiCdStack');
    template = Template.fromStack(cicdStack);
  });

  // ---------------------------------------------------------------
  // GitHub OIDC Provider — Validates: Requirements 16.13
  // ---------------------------------------------------------------

  describe('GitHub OIDC Provider', () => {
    test('exists with correct URL', () => {
      template.hasResourceProperties('Custom::AWSCDKOpenIdConnectProvider', {
        Url: 'https://token.actions.githubusercontent.com',
        ClientIDList: ['sts.amazonaws.com'],
      });
    });
  });

  // ---------------------------------------------------------------
  // IAM Role — Validates: Requirements 16.13
  // ---------------------------------------------------------------

  describe('GitHub Actions IAM Role', () => {
    test('exists with correct name', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'bbp-hkbg-github-actions-deploy',
      });
    });

    test('trusts GitHub OIDC provider via web identity federation', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'bbp-hkbg-github-actions-deploy',
        AssumeRolePolicyDocument: Match.objectLike({
          Statement: Match.arrayWith([
            Match.objectLike({
              Action: 'sts:AssumeRoleWithWebIdentity',
              Effect: 'Allow',
              Condition: Match.objectLike({
                StringEquals: Match.objectLike({
                  'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
                }),
              }),
            }),
          ]),
        }),
      });
    });
  });

  // ---------------------------------------------------------------
  // No data-read or admin permissions — Validates: Requirements 16.13
  // ---------------------------------------------------------------

  describe('CI/CD role has no data-read or admin permissions', () => {
    let allActions: string[];

    beforeAll(() => {
      const policies = template.findResources('AWS::IAM::Policy');
      allActions = [];

      for (const [, resource] of Object.entries(policies)) {
        const statements: any[] =
          (resource as any).Properties?.PolicyDocument?.Statement ?? [];
        for (const stmt of statements) {
          const actions: string[] = Array.isArray(stmt.Action)
            ? stmt.Action
            : [stmt.Action];
          allActions.push(...actions);
        }
      }
    });

    test('does NOT include DynamoDB read/write actions', () => {
      const dynamoActions = allActions.filter((a) => a.startsWith('dynamodb:'));
      expect(dynamoActions).toHaveLength(0);
    });

    test('does NOT include Cognito admin actions', () => {
      const cognitoActions = allActions.filter((a) => a.startsWith('cognito-idp:'));
      expect(cognitoActions).toHaveLength(0);
    });

    test('does NOT include Cost Explorer actions', () => {
      const ceActions = allActions.filter((a) => a.startsWith('ce:'));
      expect(ceActions).toHaveLength(0);
    });

    test('S3 access is scoped to static site bucket only, not documents bucket', () => {
      const policies = template.findResources('AWS::IAM::Policy');

      for (const [, resource] of Object.entries(policies)) {
        const statements: any[] =
          (resource as any).Properties?.PolicyDocument?.Statement ?? [];
        for (const stmt of statements) {
          const actions: string[] = Array.isArray(stmt.Action)
            ? stmt.Action
            : [stmt.Action];

          const isS3Action = actions.some((a) => a.startsWith('s3:'));
          if (!isS3Action) continue;

          const resources: any[] = Array.isArray(stmt.Resource)
            ? stmt.Resource
            : [stmt.Resource];

          for (const res of resources) {
            if (typeof res === 'string') {
              expect(res).not.toContain('bbp-hkbg-documents');
            }
          }
        }
      }
    });
  });

  // ---------------------------------------------------------------
  // Outputs — Validates: Requirements 16.13
  // ---------------------------------------------------------------

  describe('Outputs', () => {
    test('exports role ARN', () => {
      template.hasOutput('GitHubActionsRoleArn', {
        Export: { Name: 'BbpHkbgGitHubActionsRoleArn' },
      });
    });
  });
});
