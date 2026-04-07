import * as cdk from 'aws-cdk-lib';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { StorageStack } from './storage-stack';
import { ApiStack } from './api-stack';
import { AuthStack } from './auth-stack';

export interface FrontendStackProps extends cdk.StackProps {
  /** Reference to the StorageStack */
  storageStack: StorageStack;
  /** Reference to the ApiStack */
  apiStack: ApiStack;
  /** Reference to the AuthStack */
  authStack: AuthStack;
}

export class FrontendStack extends cdk.Stack {
  /** CloudFront distribution serving the SPA */
  public readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props: FrontendStackProps) {
    super(scope, id, props);

    const { storageStack, apiStack, authStack } = props;

    // Import the static site bucket by attributes within this stack to avoid
    // a circular dependency between StorageStack and FrontendStack.
    // OAC adds a bucket policy referencing the distribution, which would
    // create StorageStack → FrontendStack while FrontendStack → StorageStack
    // already exists for the bucket itself.
    const staticSiteBucket = s3.Bucket.fromBucketAttributes(this, 'StaticSiteBucketRef', {
      bucketName: storageStack.staticSiteBucket.bucketName,
      bucketArn: storageStack.staticSiteBucket.bucketArn,
      bucketRegionalDomainName: `${storageStack.staticSiteBucket.bucketName}.s3.${this.region}.amazonaws.com`,
    });

    // API Gateway origin — forward /api/* requests to the REST API.
    // The REST API stage is "prod", so we set originPath to /prod so that
    // CloudFront path /api/giveaway-years → origin /prod/api/giveaway-years.
    const apiOrigin = new origins.RestApiOrigin(apiStack.api);

    // CloudFront Function to handle SPA routing — rewrites non-file paths
    // to /index.html. This replaces custom error responses which would
    // interfere with API error status codes (401, 403, etc).
    const spaRewriteFn = new cloudfront.Function(this, 'SpaRewriteFunction', {
      code: cloudfront.FunctionCode.fromInline(`
        function handler(event) {
          var request = event.request;
          var uri = request.uri;
          if (uri.includes('.') || uri.startsWith('/api/')) {
            return request;
          }
          request.uri = '/index.html';
          return request;
        }
      `),
      runtime: cloudfront.FunctionRuntime.JS_2_0,
    });

    // CloudFront distribution — HTTPS-only, SPA rewrite via function, OAC for S3 access
    this.distribution = new cloudfront.Distribution(this, 'SiteDistribution', {
      comment: 'BBP HKBG Static Site Distribution',
      defaultRootObject: 'index.html',
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(staticSiteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        functionAssociations: [{
          function: spaRewriteFn,
          eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
        }],
      },
      additionalBehaviors: {
        '/api/*': {
          origin: apiOrigin,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
    });

    // Add bucket policy for OAC access on the imported bucket.
    // Since the bucket is imported, CDK cannot auto-generate the policy.
    // We create it explicitly in this stack to keep everything self-contained.
    const bucketPolicy = new s3.BucketPolicy(this, 'StaticSiteBucketPolicy', {
      bucket: staticSiteBucket,
    });
    bucketPolicy.document.addStatements(
      new iam.PolicyStatement({
        actions: ['s3:GetObject'],
        resources: [`${storageStack.staticSiteBucket.bucketArn}/*`],
        principals: [new iam.ServicePrincipal('cloudfront.amazonaws.com')],
        conditions: {
          StringEquals: {
            'AWS:SourceArn': `arn:aws:cloudfront::${this.account}:distribution/${this.distribution.distributionId}`,
          },
        },
      }),
    );

    // Outputs
    new cdk.CfnOutput(this, 'DistributionUrl', {
      value: `https://${this.distribution.distributionDomainName}`,
      exportName: 'BbpHkbgDistributionUrl',
    });

    new cdk.CfnOutput(this, 'DistributionId', {
      value: this.distribution.distributionId,
      exportName: 'BbpHkbgDistributionId',
    });
  }
}
