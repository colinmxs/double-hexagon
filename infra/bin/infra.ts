#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { StorageStack } from '../lib/storage-stack';
import { AuthStack } from '../lib/auth-stack';
import { ApiStack } from '../lib/api-stack';
import { FrontendStack } from '../lib/frontend-stack';
import { CiCdStack } from '../lib/cicd-stack';

const app = new cdk.App();

const storageStack = new StorageStack(app, 'BbpHkbgStorageStack', {
  description: 'BBP HKBG - S3 buckets and DynamoDB tables for application data storage',
});

const authStack = new AuthStack(app, 'BbpHkbgAuthStack', {
  description: 'BBP HKBG - Cognito User Pool with Google federation for authentication',
  storageStack,
});

const apiStack = new ApiStack(app, 'BbpHkbgApiStack', {
  description: 'BBP HKBG - API Gateway REST API with Cognito authorizer and Lambda functions',
  storageStack,
  authStack,
});

new FrontendStack(app, 'BbpHkbgFrontendStack', {
  description: 'BBP HKBG - CloudFront distribution and S3 static site hosting',
  storageStack,
  apiStack,
});

new CiCdStack(app, 'BbpHkbgCiCdStack', {
  description: 'BBP HKBG - GitHub Actions OIDC IAM role for CI/CD deployment',
});
