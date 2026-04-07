import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { StorageStack } from '../lib/storage-stack';

describe('StorageStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new StorageStack(app, 'TestStorageStack');
    template = Template.fromStack(stack);
  });

  // ---------------------------------------------------------------
  // S3 Buckets
  // ---------------------------------------------------------------

  describe('Documents Bucket', () => {
    test('has SSE-S3 encryption enabled', () => {
      template.hasResourceProperties('AWS::S3::Bucket', {
        BucketName: 'bbp-hkbg-documents',
        BucketEncryption: {
          ServerSideEncryptionConfiguration: [
            {
              ServerSideEncryptionByDefault: {
                SSEAlgorithm: 'AES256',
              },
            },
          ],
        },
      });
    });

    test('has Block Public Access enabled on all four settings', () => {
      template.hasResourceProperties('AWS::S3::Bucket', {
        BucketName: 'bbp-hkbg-documents',
        PublicAccessBlockConfiguration: {
          BlockPublicAcls: true,
          BlockPublicPolicy: true,
          IgnorePublicAcls: true,
          RestrictPublicBuckets: true,
        },
      });
    });
  });

  describe('Static Site Bucket', () => {
    test('has SSE-S3 encryption enabled', () => {
      template.hasResourceProperties('AWS::S3::Bucket', {
        BucketName: 'bbp-hkbg-static',
        BucketEncryption: {
          ServerSideEncryptionConfiguration: [
            {
              ServerSideEncryptionByDefault: {
                SSEAlgorithm: 'AES256',
              },
            },
          ],
        },
      });
    });
  });

  // ---------------------------------------------------------------
  // DynamoDB Tables — Encryption
  // ---------------------------------------------------------------

  describe('DynamoDB encryption', () => {
    test('all 5 tables have encryption at rest', () => {
      const tables = template.findResources('AWS::DynamoDB::Table');
      const tableNames = Object.keys(tables);
      expect(tableNames.length).toBe(5);

      for (const logicalId of tableNames) {
        const props = tables[logicalId].Properties;
        expect(props.SSESpecification).toBeDefined();
        expect(props.SSESpecification.SSEEnabled).toBe(true);
      }
    });
  });

  // ---------------------------------------------------------------
  // DynamoDB Tables — Key Schemas and GSIs
  // ---------------------------------------------------------------

  describe('Applications Table', () => {
    test('has application_id as partition key with no sort key', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-applications',
        KeySchema: [
          { AttributeName: 'application_id', KeyType: 'HASH' },
        ],
      });
    });

    test('has year-index GSI with giveaway_year PK and application_id SK', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-applications',
        GlobalSecondaryIndexes: Match.arrayWith([
          Match.objectLike({
            IndexName: 'year-index',
            KeySchema: [
              { AttributeName: 'giveaway_year', KeyType: 'HASH' },
              { AttributeName: 'application_id', KeyType: 'RANGE' },
            ],
          }),
        ]),
      });
    });

    test('has status-index GSI', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-applications',
        GlobalSecondaryIndexes: Match.arrayWith([
          Match.objectLike({
            IndexName: 'status-index',
            KeySchema: [
              { AttributeName: 'giveaway_year', KeyType: 'HASH' },
              { AttributeName: 'status', KeyType: 'RANGE' },
            ],
          }),
        ]),
      });
    });

    test('has agency-index GSI', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-applications',
        GlobalSecondaryIndexes: Match.arrayWith([
          Match.objectLike({
            IndexName: 'agency-index',
            KeySchema: [
              { AttributeName: 'giveaway_year', KeyType: 'HASH' },
              { AttributeName: 'referring_agency_name', KeyType: 'RANGE' },
            ],
          }),
        ]),
      });
    });

    test('has reference-index GSI with reference_number PK', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-applications',
        GlobalSecondaryIndexes: Match.arrayWith([
          Match.objectLike({
            IndexName: 'reference-index',
            KeySchema: [
              { AttributeName: 'reference_number', KeyType: 'HASH' },
            ],
          }),
        ]),
      });
    });
  });

  describe('Audit Log Table', () => {
    test('has resource_id as partition key and timestamp as sort key', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-audit-log',
        KeySchema: [
          { AttributeName: 'resource_id', KeyType: 'HASH' },
          { AttributeName: 'timestamp', KeyType: 'RANGE' },
        ],
      });
    });

    test('has user-index GSI', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-audit-log',
        GlobalSecondaryIndexes: Match.arrayWith([
          Match.objectLike({
            IndexName: 'user-index',
            KeySchema: [
              { AttributeName: 'user_id', KeyType: 'HASH' },
              { AttributeName: 'timestamp', KeyType: 'RANGE' },
            ],
          }),
        ]),
      });
    });
  });

  describe('Users Table', () => {
    test('has correct partition key', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-users',
        KeySchema: [
          { AttributeName: 'user_id', KeyType: 'HASH' },
        ],
      });
    });

    test('has email-index GSI', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-users',
        GlobalSecondaryIndexes: Match.arrayWith([
          Match.objectLike({
            IndexName: 'email-index',
            KeySchema: [
              { AttributeName: 'email', KeyType: 'HASH' },
            ],
          }),
        ]),
      });
    });
  });

  describe('Saved Reports Table', () => {
    test('has correct partition key and sort key', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-saved-reports',
        KeySchema: [
          { AttributeName: 'user_id', KeyType: 'HASH' },
          { AttributeName: 'report_id', KeyType: 'RANGE' },
        ],
      });
    });
  });

  describe('Config Table', () => {
    test('has correct partition key', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TableName: 'bbp-hkbg-config',
        KeySchema: [
          { AttributeName: 'config_key', KeyType: 'HASH' },
        ],
      });
    });
  });
});
