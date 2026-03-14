import * as cdk from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import { Construct } from 'constructs';
import { StorageStack } from './storage-stack';

export interface AuthStackProps extends cdk.StackProps {
  /** Reference to the StorageStack for cross-stack dependency */
  storageStack: StorageStack;
}

export class AuthStack extends cdk.Stack {
  /** Cognito User Pool for authentication */
  public readonly userPool: cognito.UserPool;
  /** App Client for the SPA */
  public readonly userPoolClient: cognito.UserPoolClient;
  /** User Pool domain for hosted UI */
  public readonly userPoolDomain: cognito.UserPoolDomain;
  /** Google identity provider */
  public readonly googleProvider: cognito.UserPoolIdentityProviderGoogle;

  constructor(scope: Construct, id: string, props: AuthStackProps) {
    super(scope, id, props);

    // Parameterize Google OAuth credentials — never hardcode secrets
    const googleClientId = new cdk.CfnParameter(this, 'GoogleClientId', {
      type: 'String',
      description: 'Google OAuth 2.0 Client ID for federated sign-in',
      noEcho: true,
    });

    const googleClientSecret = new cdk.CfnParameter(this, 'GoogleClientSecret', {
      type: 'String',
      description: 'Google OAuth 2.0 Client Secret for federated sign-in',
      noEcho: true,
    });

    const callbackUrl = new cdk.CfnParameter(this, 'CallbackUrl', {
      type: 'String',
      description: 'OAuth callback URL for the SPA (e.g. https://example.com/callback)',
      default: 'http://localhost:5173/callback',
    });

    const logoutUrl = new cdk.CfnParameter(this, 'LogoutUrl', {
      type: 'String',
      description: 'OAuth logout URL for the SPA (e.g. https://example.com)',
      default: 'http://localhost:5173',
    });

    // Cognito User Pool — native username/password sign-in
    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: 'bbp-hkbg-user-pool',
      selfSignUpEnabled: false, // Admin-created accounts only
      signInAliases: {
        username: true,
        email: true,
      },
      autoVerify: {
        email: true,
      },
      standardAttributes: {
        email: {
          required: true,
          mutable: true,
        },
        fullname: {
          required: false,
          mutable: true,
        },
      },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
        tempPasswordValidity: cdk.Duration.days(7),
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Google as federated identity provider
    this.googleProvider = new cognito.UserPoolIdentityProviderGoogle(this, 'GoogleProvider', {
      userPool: this.userPool,
      clientId: googleClientId.valueAsString,
      clientSecretValue: cdk.SecretValue.unsafePlainText(googleClientSecret.valueAsString),
      scopes: ['profile', 'email', 'openid'],
      attributeMapping: {
        email: cognito.ProviderAttribute.GOOGLE_EMAIL,
        fullname: cognito.ProviderAttribute.GOOGLE_NAME,
      },
    });

    // Hosted UI domain for OAuth flows
    this.userPoolDomain = this.userPool.addDomain('UserPoolDomain', {
      cognitoDomain: {
        domainPrefix: 'bbp-hkbg',
      },
    });

    // App Client for the SPA — OAuth 2.0 / OIDC configuration
    this.userPoolClient = this.userPool.addClient('SpaClient', {
      userPoolClientName: 'bbp-hkbg-spa-client',
      generateSecret: false, // Public client for SPA (no client secret)
      authFlows: {
        userPassword: true,
        userSrp: true,
      },
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
          implicitCodeGrant: false,
        },
        scopes: [
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: [callbackUrl.valueAsString],
        logoutUrls: [logoutUrl.valueAsString],
      },
      supportedIdentityProviders: [
        cognito.UserPoolClientIdentityProvider.COGNITO,
        cognito.UserPoolClientIdentityProvider.GOOGLE,
      ],
      preventUserExistenceErrors: true,
    });

    // Ensure the Google provider is created before the client references it
    this.userPoolClient.node.addDependency(this.googleProvider);

    // Outputs for downstream stacks
    new cdk.CfnOutput(this, 'UserPoolId', {
      value: this.userPool.userPoolId,
      exportName: 'BbpHkbgUserPoolId',
    });

    new cdk.CfnOutput(this, 'UserPoolArn', {
      value: this.userPool.userPoolArn,
      exportName: 'BbpHkbgUserPoolArn',
    });

    new cdk.CfnOutput(this, 'UserPoolClientId', {
      value: this.userPoolClient.userPoolClientId,
      exportName: 'BbpHkbgUserPoolClientId',
    });

    new cdk.CfnOutput(this, 'UserPoolDomainName', {
      value: this.userPoolDomain.domainName,
      exportName: 'BbpHkbgUserPoolDomainName',
    });
  }
}
