import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { StorageStack } from '../lib/storage-stack';
import { AuthStack } from '../lib/auth-stack';

describe('AuthStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const storageStack = new StorageStack(app, 'TestStorageStack');
    const authStack = new AuthStack(app, 'TestAuthStack', {
      storageStack,
    });
    template = Template.fromStack(authStack);
  });

  // ---------------------------------------------------------------
  // Cognito User Pool
  // ---------------------------------------------------------------

  describe('User Pool', () => {
    test('exists with correct name', () => {
      template.hasResourceProperties('AWS::Cognito::UserPool', {
        UserPoolName: 'bbp-hkbg-user-pool',
      });
    });

    test('has self-signup disabled', () => {
      template.hasResourceProperties('AWS::Cognito::UserPool', {
        AdminCreateUserConfig: {
          AllowAdminCreateUserOnly: true,
        },
      });
    });

    test('has password policy with min length 8 and all complexity requirements', () => {
      template.hasResourceProperties('AWS::Cognito::UserPool', {
        Policies: {
          PasswordPolicy: {
            MinimumLength: 8,
            RequireLowercase: true,
            RequireUppercase: true,
            RequireNumbers: true,
            RequireSymbols: true,
          },
        },
      });
    });
  });

  // ---------------------------------------------------------------
  // Google Identity Provider
  // ---------------------------------------------------------------

  describe('Google Identity Provider', () => {
    test('is configured', () => {
      template.hasResourceProperties('AWS::Cognito::UserPoolIdentityProvider', {
        ProviderName: 'Google',
        ProviderType: 'Google',
      });
    });
  });

  // ---------------------------------------------------------------
  // App Client
  // ---------------------------------------------------------------

  describe('App Client', () => {
    test('exists with correct name', () => {
      template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
        ClientName: 'bbp-hkbg-spa-client',
      });
    });

    test('does not generate a client secret', () => {
      template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
        GenerateSecret: false,
      });
    });

    test('supports authorization code grant', () => {
      template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
        AllowedOAuthFlows: Match.arrayWith(['code']),
      });
    });

    test('supports Cognito and Google identity providers', () => {
      template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
        SupportedIdentityProviders: Match.arrayWith(['COGNITO', 'Google']),
      });
    });
  });

  // ---------------------------------------------------------------
  // User Pool Domain
  // ---------------------------------------------------------------

  describe('User Pool Domain', () => {
    test('is configured', () => {
      template.hasResourceProperties('AWS::Cognito::UserPoolDomain', {
        Domain: 'bbp-hkbg',
      });
    });
  });

  // ---------------------------------------------------------------
  // Outputs
  // ---------------------------------------------------------------

  describe('Outputs', () => {
    test('exports UserPoolId', () => {
      template.hasOutput('UserPoolId', {
        Export: { Name: 'BbpHkbgUserPoolId' },
      });
    });

    test('exports UserPoolClientId', () => {
      template.hasOutput('UserPoolClientId', {
        Export: { Name: 'BbpHkbgUserPoolClientId' },
      });
    });
  });
});
