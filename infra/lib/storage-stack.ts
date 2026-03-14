import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

export class StorageStack extends cdk.Stack {
  /** Documents bucket for uploads, drawings, versions, and exports */
  public readonly documentsBucket: s3.Bucket;
  /** Static site bucket for hosting the Vue.js SPA */
  public readonly staticSiteBucket: s3.Bucket;
  /** DynamoDB table for application records */
  public readonly applicationsTable: dynamodb.Table;
  /** DynamoDB table for audit log entries */
  public readonly auditLogTable: dynamodb.Table;
  /** DynamoDB table for user accounts */
  public readonly usersTable: dynamodb.Table;
  /** DynamoDB table for saved report configurations */
  public readonly savedReportsTable: dynamodb.Table;
  /** DynamoDB table for system configuration */
  public readonly configTable: dynamodb.Table;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Documents bucket — stores uploaded files, cropped drawings, record versions, and exports
    this.documentsBucket = new s3.Bucket(this, 'DocumentsBucket', {
      bucketName: 'bbp-hkbg-documents',
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [
        {
          id: 'GlacierTransition',
          prefix: 'uploads/',
          transitions: [
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(365),
            },
          ],
        },
        {
          id: 'DrawingsGlacierTransition',
          prefix: 'drawings/',
          transitions: [
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(365),
            },
          ],
        },
        {
          id: 'VersionsGlacierTransition',
          prefix: 'versions/',
          transitions: [
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(365),
            },
          ],
        },
        {
          id: 'ExportsCleanup',
          prefix: 'exports/',
          expiration: cdk.Duration.days(7),
        },
      ],
    });

    // Static site bucket — hosts the Vue.js SPA served via CloudFront
    this.staticSiteBucket = new s3.Bucket(this, 'StaticSiteBucket', {
      bucketName: 'bbp-hkbg-static',
      encryption: s3.BucketEncryption.S3_MANAGED,
      websiteIndexDocument: 'index.html',
      websiteErrorDocument: 'index.html',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Outputs for downstream stacks
    new cdk.CfnOutput(this, 'DocumentsBucketName', {
      value: this.documentsBucket.bucketName,
      exportName: 'BbpHkbgDocumentsBucketName',
    });

    new cdk.CfnOutput(this, 'DocumentsBucketArn', {
      value: this.documentsBucket.bucketArn,
      exportName: 'BbpHkbgDocumentsBucketArn',
    });

    new cdk.CfnOutput(this, 'StaticSiteBucketName', {
      value: this.staticSiteBucket.bucketName,
      exportName: 'BbpHkbgStaticSiteBucketName',
    });

    new cdk.CfnOutput(this, 'StaticSiteUrl', {
      value: this.staticSiteBucket.bucketWebsiteUrl,
      exportName: 'BbpHkbgStaticSiteUrl',
    });

    // ---------------------------------------------------------------
    // DynamoDB Tables
    // ---------------------------------------------------------------

    // Applications table — stores all application records partitioned by giveaway year
    this.applicationsTable = new dynamodb.Table(this, 'ApplicationsTable', {
      tableName: 'bbp-hkbg-applications',
      partitionKey: { name: 'giveaway_year', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'application_id', type: dynamodb.AttributeType.STRING },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.applicationsTable.addGlobalSecondaryIndex({
      indexName: 'status-index',
      partitionKey: { name: 'giveaway_year', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'status', type: dynamodb.AttributeType.STRING },
    });

    this.applicationsTable.addGlobalSecondaryIndex({
      indexName: 'agency-index',
      partitionKey: { name: 'giveaway_year', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'referring_agency_name', type: dynamodb.AttributeType.STRING },
    });

    // Audit Log table — dedicated table for audit trail entries
    this.auditLogTable = new dynamodb.Table(this, 'AuditLogTable', {
      tableName: 'bbp-hkbg-audit-log',
      partitionKey: { name: 'year_month', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp#user_id', type: dynamodb.AttributeType.STRING },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.auditLogTable.addGlobalSecondaryIndex({
      indexName: 'user-index',
      partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
    });

    this.auditLogTable.addGlobalSecondaryIndex({
      indexName: 'action-index',
      partitionKey: { name: 'action_type', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
    });

    // Users table — stores user accounts and roles
    this.usersTable = new dynamodb.Table(this, 'UsersTable', {
      tableName: 'bbp-hkbg-users',
      partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    this.usersTable.addGlobalSecondaryIndex({
      indexName: 'email-index',
      partitionKey: { name: 'email', type: dynamodb.AttributeType.STRING },
    });

    // Saved Reports table — stores user report configurations
    this.savedReportsTable = new dynamodb.Table(this, 'SavedReportsTable', {
      tableName: 'bbp-hkbg-saved-reports',
      partitionKey: { name: 'user_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'report_id', type: dynamodb.AttributeType.STRING },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Config table — stores system configuration key-value pairs
    this.configTable = new dynamodb.Table(this, 'ConfigTable', {
      tableName: 'bbp-hkbg-config',
      partitionKey: { name: 'config_key', type: dynamodb.AttributeType.STRING },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // DynamoDB Outputs — table names and ARNs for downstream stacks
    new cdk.CfnOutput(this, 'ApplicationsTableName', {
      value: this.applicationsTable.tableName,
      exportName: 'BbpHkbgApplicationsTableName',
    });
    new cdk.CfnOutput(this, 'ApplicationsTableArn', {
      value: this.applicationsTable.tableArn,
      exportName: 'BbpHkbgApplicationsTableArn',
    });

    new cdk.CfnOutput(this, 'AuditLogTableName', {
      value: this.auditLogTable.tableName,
      exportName: 'BbpHkbgAuditLogTableName',
    });
    new cdk.CfnOutput(this, 'AuditLogTableArn', {
      value: this.auditLogTable.tableArn,
      exportName: 'BbpHkbgAuditLogTableArn',
    });

    new cdk.CfnOutput(this, 'UsersTableName', {
      value: this.usersTable.tableName,
      exportName: 'BbpHkbgUsersTableName',
    });
    new cdk.CfnOutput(this, 'UsersTableArn', {
      value: this.usersTable.tableArn,
      exportName: 'BbpHkbgUsersTableArn',
    });

    new cdk.CfnOutput(this, 'SavedReportsTableName', {
      value: this.savedReportsTable.tableName,
      exportName: 'BbpHkbgSavedReportsTableName',
    });
    new cdk.CfnOutput(this, 'SavedReportsTableArn', {
      value: this.savedReportsTable.tableArn,
      exportName: 'BbpHkbgSavedReportsTableArn',
    });

    new cdk.CfnOutput(this, 'ConfigTableName', {
      value: this.configTable.tableName,
      exportName: 'BbpHkbgConfigTableName',
    });
    new cdk.CfnOutput(this, 'ConfigTableArn', {
      value: this.configTable.tableArn,
      exportName: 'BbpHkbgConfigTableArn',
    });
  }
}
