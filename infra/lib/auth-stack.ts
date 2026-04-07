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

  constructor(scope: Construct, id: string, props: AuthStackProps) {
    super(scope, id, props);

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

    // App Client — username/password only (COGNITO provider)
    this.userPoolClient = this.userPool.addClient('SpaClient', {
      userPoolClientName: 'bbp-hkbg-spa-client',
      generateSecret: false, // Public client for SPA (no client secret)
      authFlows: {
        userPassword: true,
        userSrp: true,
      },
      supportedIdentityProviders: [
        cognito.UserPoolClientIdentityProvider.COGNITO,
      ],
      preventUserExistenceErrors: true,
    });

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
  }
}
