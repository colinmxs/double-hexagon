import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class CiCdStack extends cdk.Stack {
  /** IAM role assumed by GitHub Actions via OIDC federation */
  public readonly gitHubActionsRole: iam.Role;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ---------------------------------------------------------------
    // Configurable parameters for GitHub org/repo
    // ---------------------------------------------------------------

    const githubOrg = new cdk.CfnParameter(this, 'GitHubOrg', {
      type: 'String',
      description: 'GitHub organization or user name',
      default: 'my-org',
    });

    const githubRepo = new cdk.CfnParameter(this, 'GitHubRepo', {
      type: 'String',
      description: 'GitHub repository name',
      default: 'bbp-hkbg',
    });

    // ---------------------------------------------------------------
    // GitHub Actions OIDC Provider
    // ---------------------------------------------------------------

    const oidcProvider = new iam.OpenIdConnectProvider(this, 'GitHubOidcProvider', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
      thumbprints: ['6938fd4d98bab03faadb97b34396831e3780aea1'],
    });

    // ---------------------------------------------------------------
    // IAM Role for GitHub Actions — deployment-only permissions
    // ---------------------------------------------------------------

    this.gitHubActionsRole = new iam.Role(this, 'GitHubActionsDeployRole', {
      roleName: 'bbp-hkbg-github-actions-deploy',
      description: 'Deployment-only role for GitHub Actions CI/CD pipeline (OIDC federation)',
      assumedBy: new iam.FederatedPrincipal(
        oidcProvider.openIdConnectProviderArn,
        {
          StringEquals: {
            'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
          },
          StringLike: {
            'token.actions.githubusercontent.com:sub': `repo:${githubOrg.valueAsString}/${githubRepo.valueAsString}:*`,
          },
        },
        'sts:AssumeRoleWithWebIdentity',
      ),
      maxSessionDuration: cdk.Duration.hours(1),
    });

    // ---------------------------------------------------------------
    // CloudFormation — required for CDK deploy
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'CloudFormationDeploy',
      actions: [
        'cloudformation:CreateStack',
        'cloudformation:UpdateStack',
        'cloudformation:DeleteStack',
        'cloudformation:DescribeStacks',
        'cloudformation:DescribeStackEvents',
        'cloudformation:DescribeStackResources',
        'cloudformation:GetTemplate',
        'cloudformation:GetTemplateSummary',
        'cloudformation:ValidateTemplate',
        'cloudformation:CreateChangeSet',
        'cloudformation:DescribeChangeSet',
        'cloudformation:ExecuteChangeSet',
        'cloudformation:DeleteChangeSet',
        'cloudformation:ListStacks',
      ],
      resources: [
        `arn:aws:cloudformation:${this.region}:${this.account}:stack/BbpHkbg*/*`,
      ],
    }));

    // ---------------------------------------------------------------
    // Lambda — update function code and configuration only
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'LambdaDeploy',
      actions: [
        'lambda:UpdateFunctionCode',
        'lambda:UpdateFunctionConfiguration',
        'lambda:GetFunction',
        'lambda:GetFunctionConfiguration',
        'lambda:ListFunctions',
        'lambda:CreateFunction',
        'lambda:DeleteFunction',
        'lambda:AddPermission',
        'lambda:RemovePermission',
        'lambda:TagResource',
        'lambda:UntagResource',
        'lambda:ListTags',
        'lambda:PublishVersion',
        'lambda:CreateAlias',
        'lambda:UpdateAlias',
        'lambda:GetAlias',
      ],
      resources: [
        `arn:aws:lambda:${this.region}:${this.account}:function:bbp-hkbg-*`,
      ],
    }));

    // ---------------------------------------------------------------
    // S3 — put objects to static site bucket only (not documents bucket)
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3StaticSiteDeploy',
      actions: [
        's3:PutObject',
        's3:DeleteObject',
        's3:GetObject',
        's3:ListBucket',
        's3:GetBucketLocation',
      ],
      resources: [
        'arn:aws:s3:::bbp-hkbg-static',
        'arn:aws:s3:::bbp-hkbg-static/*',
      ],
    }));

    // S3 access for CDK staging bucket (asset uploads)
    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'S3CdkStagingBucket',
      actions: [
        's3:PutObject',
        's3:GetObject',
        's3:ListBucket',
        's3:GetBucketLocation',
        's3:CreateBucket',
      ],
      resources: [
        `arn:aws:s3:::cdk-*-assets-${this.account}-${this.region}`,
        `arn:aws:s3:::cdk-*-assets-${this.account}-${this.region}/*`,
      ],
    }));

    // ---------------------------------------------------------------
    // CloudFront — create invalidation only
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'CloudFrontInvalidation',
      actions: [
        'cloudfront:CreateInvalidation',
        'cloudfront:GetInvalidation',
        'cloudfront:ListInvalidations',
      ],
      resources: [
        `arn:aws:cloudfront::${this.account}:distribution/*`,
      ],
    }));

    // ---------------------------------------------------------------
    // API Gateway — deployment operations
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'ApiGatewayDeploy',
      actions: [
        'apigateway:GET',
        'apigateway:POST',
        'apigateway:PUT',
        'apigateway:PATCH',
        'apigateway:DELETE',
      ],
      resources: [
        `arn:aws:apigateway:${this.region}::/restapis`,
        `arn:aws:apigateway:${this.region}::/restapis/*`,
      ],
    }));

    // ---------------------------------------------------------------
    // IAM — pass role for Lambda execution roles only
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'IamPassRole',
      actions: ['iam:PassRole'],
      resources: [
        `arn:aws:iam::${this.account}:role/BbpHkbg*`,
      ],
      conditions: {
        StringEquals: {
          'iam:PassedToService': 'lambda.amazonaws.com',
        },
      },
    }));

    // IAM role management for CDK-created roles
    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'IamRoleManagement',
      actions: [
        'iam:GetRole',
        'iam:CreateRole',
        'iam:DeleteRole',
        'iam:AttachRolePolicy',
        'iam:DetachRolePolicy',
        'iam:PutRolePolicy',
        'iam:DeleteRolePolicy',
        'iam:GetRolePolicy',
        'iam:TagRole',
        'iam:UntagRole',
      ],
      resources: [
        `arn:aws:iam::${this.account}:role/BbpHkbg*`,
      ],
    }));

    // ---------------------------------------------------------------
    // SSM — parameter store for CDK bootstrap and stack outputs
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'SsmParameterAccess',
      actions: [
        'ssm:GetParameter',
        'ssm:GetParameters',
        'ssm:PutParameter',
      ],
      resources: [
        `arn:aws:ssm:${this.region}:${this.account}:parameter/cdk-bootstrap/*`,
      ],
    }));

    // ---------------------------------------------------------------
    // STS — for CDK to assume roles during deployment
    // ---------------------------------------------------------------

    this.gitHubActionsRole.addToPolicy(new iam.PolicyStatement({
      sid: 'StsAssumeRole',
      actions: ['sts:AssumeRole'],
      resources: [
        `arn:aws:iam::${this.account}:role/cdk-*-${this.region}`,
      ],
    }));

    // ---------------------------------------------------------------
    // Outputs
    // ---------------------------------------------------------------

    new cdk.CfnOutput(this, 'GitHubActionsRoleArn', {
      value: this.gitHubActionsRole.roleArn,
      exportName: 'BbpHkbgGitHubActionsRoleArn',
      description: 'ARN of the IAM role for GitHub Actions OIDC federation',
    });

    new cdk.CfnOutput(this, 'OidcProviderArn', {
      value: oidcProvider.openIdConnectProviderArn,
      exportName: 'BbpHkbgGitHubOidcProviderArn',
      description: 'ARN of the GitHub Actions OIDC provider',
    });
  }
}
