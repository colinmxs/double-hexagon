import * as cdk from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import { Construct } from 'constructs';
import { StorageStack } from './storage-stack';
import { AuthStack } from './auth-stack';
import * as path from 'path';

export interface ApiStackProps extends cdk.StackProps {
  /** Reference to the StorageStack */
  storageStack: StorageStack;
  /** Reference to the AuthStack */
  authStack: AuthStack;
  /** Allowed CORS origins (e.g. ['https://app.example.com', 'http://localhost:5173']) */
  allowedOrigins?: string[];
}

export class ApiStack extends cdk.Stack {
  /** The REST API */
  public readonly api: apigateway.RestApi;
  /** Cognito User Pool authorizer for authenticated endpoints */
  public readonly cognitoAuthorizer: apigateway.CognitoUserPoolsAuthorizer;

  // Lambda functions — exposed for testing and downstream references
  public readonly submitApplicationFn: lambda.Function;
  public readonly generatePresignedUrlFn: lambda.Function;
  public readonly processDocumentFn: lambda.Function;
  public readonly getApplicationsFn: lambda.Function;
  public readonly getApplicationDetailFn: lambda.Function;
  public readonly updateApplicationFn: lambda.Function;
  public readonly exportDataFn: lambda.Function;
  public readonly manageReportsFn: lambda.Function;
  public readonly runReportFn: lambda.Function;
  public readonly getCostDataFn: lambda.Function;
  public readonly manageUsersFn: lambda.Function;
  public readonly getAuditLogFn: lambda.Function;
  public readonly manageGiveawayYearFn: lambda.Function;
  public readonly getAuthMeFn: lambda.Function;

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    const { storageStack, authStack } = props;

    const allowedOrigins = props.allowedOrigins ?? ['http://localhost:5173', 'http://localhost:4173'];
    const allowedOriginsEnv = allowedOrigins.join(',');

    // Shorthand references
    const applicationsTable = storageStack.applicationsTable;
    const auditLogTable = storageStack.auditLogTable;
    const usersTable = storageStack.usersTable;
    const savedReportsTable = storageStack.savedReportsTable;
    const configTable = storageStack.configTable;
    const documentsBucket = storageStack.documentsBucket;
    const userPool = authStack.userPool;

    const lambdaDir = path.join(__dirname, '..', '..', 'lambda');

    // ---------------------------------------------------------------
    // REST API
    // ---------------------------------------------------------------

    this.api = new apigateway.RestApi(this, 'BbpHkbgApi', {
      restApiName: 'bbp-hkbg-api',
      description: 'BBP Holiday Kids Bike Giveaway REST API',
      deployOptions: {
        stageName: 'prod',
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: allowedOrigins,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: [
          'Content-Type',
          'Authorization',
          'X-Amz-Date',
          'X-Api-Key',
          'X-Amz-Security-Token',
        ],
        allowCredentials: true,
      },
    });

    // ---------------------------------------------------------------
    // Cognito Authorizer
    // ---------------------------------------------------------------

    this.cognitoAuthorizer = new apigateway.CognitoUserPoolsAuthorizer(this, 'CognitoAuthorizer', {
      cognitoUserPools: [userPool],
      authorizerName: 'bbp-hkbg-cognito-authorizer',
      identitySource: 'method.request.header.Authorization',
    });

    const authMethodOptions: apigateway.MethodOptions = {
      authorizer: this.cognitoAuthorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO,
    };

    // ---------------------------------------------------------------
    // Lambda Functions with per-function IAM roles
    // ---------------------------------------------------------------

    // 1. submit_application — DynamoDB write (applications + audit log)
    this.submitApplicationFn = new lambda.Function(this, 'SubmitApplicationFn', {
      functionName: 'bbp-hkbg-submit-application',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'submit_application')),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    applicationsTable.grantWriteData(this.submitApplicationFn);
    auditLogTable.grantWriteData(this.submitApplicationFn);

    // 2. generate_presigned_url — S3 PutObject on documents bucket
    this.generatePresignedUrlFn = new lambda.Function(this, 'GeneratePresignedUrlFn', {
      functionName: 'bbp-hkbg-generate-presigned-url',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'generate_presigned_url')),
      timeout: cdk.Duration.seconds(15),
      memorySize: 128,
      environment: {
        DOCUMENTS_BUCKET_NAME: documentsBucket.bucketName,
        AUTH_ENABLED: 'true',
      },
    });
    documentsBucket.grantPut(this.generatePresignedUrlFn, 'uploads/*');

    // 3. process_document — Textract, Bedrock, S3 read/write, DynamoDB write
    this.processDocumentFn = new lambda.Function(this, 'ProcessDocumentFn', {
      functionName: 'bbp-hkbg-process-document',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'process_document')),
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        DOCUMENTS_BUCKET_NAME: documentsBucket.bucketName,
        AUTH_ENABLED: 'true',
      },
    });
    applicationsTable.grantWriteData(this.processDocumentFn);
    auditLogTable.grantWriteData(this.processDocumentFn);
    documentsBucket.grantReadWrite(this.processDocumentFn);
    this.processDocumentFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['textract:AnalyzeDocument', 'textract:DetectDocumentText'],
      resources: ['*'], // Textract does not support resource-level permissions
    }));
    this.processDocumentFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:InvokeModel'],
      resources: [
        `arn:aws:bedrock:${this.region}::foundation-model/*`,
      ],
    }));

    // 4. get_applications — DynamoDB read (applications + users)
    this.getApplicationsFn = new lambda.Function(this, 'GetApplicationsFn', {
      functionName: 'bbp-hkbg-get-applications',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'get_applications')),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        USERS_TABLE_NAME: usersTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    applicationsTable.grantReadData(this.getApplicationsFn);
    usersTable.grantReadData(this.getApplicationsFn);

    // 5. get_application_detail — DynamoDB read (applications), S3 read (presigned), audit log write
    this.getApplicationDetailFn = new lambda.Function(this, 'GetApplicationDetailFn', {
      functionName: 'bbp-hkbg-get-application-detail',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'get_application_detail')),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        DOCUMENTS_BUCKET_NAME: documentsBucket.bucketName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    applicationsTable.grantReadData(this.getApplicationDetailFn);
    auditLogTable.grantWriteData(this.getApplicationDetailFn);
    documentsBucket.grantRead(this.getApplicationDetailFn);

    // 6. update_application — DynamoDB read/write (applications), S3 write (versions), audit log write
    this.updateApplicationFn = new lambda.Function(this, 'UpdateApplicationFn', {
      functionName: 'bbp-hkbg-update-application',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'update_application')),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        DOCUMENTS_BUCKET_NAME: documentsBucket.bucketName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    applicationsTable.grantReadWriteData(this.updateApplicationFn);
    auditLogTable.grantWriteData(this.updateApplicationFn);
    documentsBucket.grantWrite(this.updateApplicationFn, 'versions/*');

    // 7. export_data — DynamoDB read (applications), audit log write
    this.exportDataFn = new lambda.Function(this, 'ExportDataFn', {
      functionName: 'bbp-hkbg-export-data',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'export_data')),
      timeout: cdk.Duration.seconds(60),
      memorySize: 256,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    applicationsTable.grantReadData(this.exportDataFn);
    auditLogTable.grantWriteData(this.exportDataFn);

    // 8. manage_reports — DynamoDB read/write (saved reports)
    this.manageReportsFn = new lambda.Function(this, 'ManageReportsFn', {
      functionName: 'bbp-hkbg-manage-reports',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'manage_reports')),
      timeout: cdk.Duration.seconds(15),
      memorySize: 128,
      environment: {
        SAVED_REPORTS_TABLE_NAME: savedReportsTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    savedReportsTable.grantReadWriteData(this.manageReportsFn);

    // 9. run_report — DynamoDB read (applications + users)
    this.runReportFn = new lambda.Function(this, 'RunReportFn', {
      functionName: 'bbp-hkbg-run-report',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'run_report')),
      timeout: cdk.Duration.seconds(60),
      memorySize: 256,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        USERS_TABLE_NAME: usersTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    applicationsTable.grantReadData(this.runReportFn);
    usersTable.grantReadData(this.runReportFn);

    // 10. get_cost_data — Cost Explorer read, DynamoDB read/write (config)
    this.getCostDataFn = new lambda.Function(this, 'GetCostDataFn', {
      functionName: 'bbp-hkbg-get-cost-data',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'get_cost_data')),
      timeout: cdk.Duration.seconds(30),
      memorySize: 128,
      environment: {
        CONFIG_TABLE_NAME: configTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    configTable.grantReadWriteData(this.getCostDataFn);
    this.getCostDataFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['ce:GetCostAndUsage'],
      resources: ['*'], // Cost Explorer does not support resource-level permissions
    }));

    // 11. manage_users — DynamoDB read/write (users), Cognito admin, audit log write
    this.manageUsersFn = new lambda.Function(this, 'ManageUsersFn', {
      functionName: 'bbp-hkbg-manage-users',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'manage_users')),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        USERS_TABLE_NAME: usersTable.tableName,
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    usersTable.grantReadWriteData(this.manageUsersFn);
    auditLogTable.grantWriteData(this.manageUsersFn);
    this.manageUsersFn.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'cognito-idp:AdminCreateUser',
        'cognito-idp:AdminDeleteUser',
        'cognito-idp:AdminDisableUser',
        'cognito-idp:AdminEnableUser',
        'cognito-idp:AdminGetUser',
        'cognito-idp:AdminResetUserPassword',
        'cognito-idp:AdminUpdateUserAttributes',
        'cognito-idp:ListUsers',
      ],
      resources: [userPool.userPoolArn],
    }));

    // 12. get_audit_log — DynamoDB read (audit log)
    this.getAuditLogFn = new lambda.Function(this, 'GetAuditLogFn', {
      functionName: 'bbp-hkbg-get-audit-log',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'get_audit_log')),
      timeout: cdk.Duration.seconds(30),
      memorySize: 128,
      environment: {
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    auditLogTable.grantReadData(this.getAuditLogFn);

    // 13. manage_giveaway_year — DynamoDB read/write (applications + config), S3 lifecycle/delete, S3 Glacier, audit log write
    this.manageGiveawayYearFn = new lambda.Function(this, 'ManageGiveawayYearFn', {
      functionName: 'bbp-hkbg-manage-giveaway-year',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'manage_giveaway_year')),
      timeout: cdk.Duration.minutes(5),
      memorySize: 256,
      environment: {
        APPLICATIONS_TABLE_NAME: applicationsTable.tableName,
        CONFIG_TABLE_NAME: configTable.tableName,
        AUDIT_LOG_TABLE_NAME: auditLogTable.tableName,
        DOCUMENTS_BUCKET_NAME: documentsBucket.bucketName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    applicationsTable.grantReadWriteData(this.manageGiveawayYearFn);
    configTable.grantReadWriteData(this.manageGiveawayYearFn);
    auditLogTable.grantWriteData(this.manageGiveawayYearFn);
    documentsBucket.grantReadWrite(this.manageGiveawayYearFn);
    documentsBucket.grantDelete(this.manageGiveawayYearFn);
    this.manageGiveawayYearFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['s3:PutLifecycleConfiguration', 's3:GetLifecycleConfiguration'],
      resources: [documentsBucket.bucketArn],
    }));

    // 14. get_auth_me — DynamoDB read (users)
    this.getAuthMeFn = new lambda.Function(this, 'GetAuthMeFn', {
      functionName: 'bbp-hkbg-get-auth-me',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(lambdaDir, 'get_auth_me')),
      timeout: cdk.Duration.seconds(15),
      memorySize: 128,
      environment: {
        USERS_TABLE_NAME: usersTable.tableName,
        AUTH_ENABLED: 'true',
        USER_POOL_ID: userPool.userPoolId,
      },
    });
    usersTable.grantReadData(this.getAuthMeFn);

    // ---------------------------------------------------------------
    // Inject ALLOWED_ORIGINS into all Lambda functions
    // ---------------------------------------------------------------
    const allFunctions = [
      this.submitApplicationFn, this.generatePresignedUrlFn, this.processDocumentFn,
      this.getApplicationsFn, this.getApplicationDetailFn, this.updateApplicationFn,
      this.exportDataFn, this.manageReportsFn, this.runReportFn, this.getCostDataFn,
      this.manageUsersFn, this.getAuditLogFn, this.manageGiveawayYearFn, this.getAuthMeFn,
    ];
    for (const fn of allFunctions) {
      fn.addEnvironment('ALLOWED_ORIGINS', allowedOriginsEnv);
    }

    // ---------------------------------------------------------------
    // S3 Event Notification — trigger process_document on uploads/
    // ---------------------------------------------------------------
    // Import the bucket by attributes within this stack to avoid the circular
    // dependency that bucket.addEventNotification would create when the bucket
    // lives in StorageStack and the Lambda lives here in ApiStack.
    const documentsBucketForNotification = s3.Bucket.fromBucketAttributes(this, 'DocumentsBucketRef', {
      bucketName: documentsBucket.bucketName,
      bucketArn: documentsBucket.bucketArn,
    });
    documentsBucketForNotification.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(this.processDocumentFn),
      { prefix: 'uploads/' },
    );

    // ---------------------------------------------------------------
    // Lambda Integrations
    // ---------------------------------------------------------------

    const submitApplicationIntegration = new apigateway.LambdaIntegration(this.submitApplicationFn);
    const generatePresignedUrlIntegration = new apigateway.LambdaIntegration(this.generatePresignedUrlFn);
    const getApplicationsIntegration = new apigateway.LambdaIntegration(this.getApplicationsFn);
    const getApplicationDetailIntegration = new apigateway.LambdaIntegration(this.getApplicationDetailFn);
    const updateApplicationIntegration = new apigateway.LambdaIntegration(this.updateApplicationFn);
    const exportDataIntegration = new apigateway.LambdaIntegration(this.exportDataFn);
    const manageReportsIntegration = new apigateway.LambdaIntegration(this.manageReportsFn);
    const runReportIntegration = new apigateway.LambdaIntegration(this.runReportFn);
    const getCostDataIntegration = new apigateway.LambdaIntegration(this.getCostDataFn);
    const manageUsersIntegration = new apigateway.LambdaIntegration(this.manageUsersFn);
    const getAuditLogIntegration = new apigateway.LambdaIntegration(this.getAuditLogFn);
    const manageGiveawayYearIntegration = new apigateway.LambdaIntegration(this.manageGiveawayYearFn);
    const getAuthMeIntegration = new apigateway.LambdaIntegration(this.getAuthMeFn);

    // ---------------------------------------------------------------
    // API Resources and Methods
    // ---------------------------------------------------------------

    const apiRoot = this.api.root.addResource('api');

    // --- Applications ---
    const applications = apiRoot.addResource('applications');
    applications.addMethod('POST', submitApplicationIntegration);
    applications.addMethod('GET', getApplicationsIntegration, authMethodOptions);

    const applicationById = applications.addResource('{id}');
    applicationById.addMethod('GET', getApplicationDetailIntegration, authMethodOptions);
    applicationById.addMethod('PUT', updateApplicationIntegration, authMethodOptions);

    const applicationStatus = applicationById.addResource('status');
    applicationStatus.addMethod('PUT', updateApplicationIntegration, authMethodOptions);

    const children = applicationById.addResource('children');
    const childById = children.addResource('{childId}');
    const bikeNumber = childById.addResource('bike-number');
    bikeNumber.addMethod('PUT', updateApplicationIntegration, authMethodOptions);
    const drawingKeywords = childById.addResource('drawing-keywords');
    drawingKeywords.addMethod('PUT', updateApplicationIntegration, authMethodOptions);

    // --- Uploads ---
    const uploads = apiRoot.addResource('uploads');
    const presign = uploads.addResource('presign');
    presign.addMethod('POST', generatePresignedUrlIntegration);

    // --- Exports ---
    const exports_ = apiRoot.addResource('exports');
    const bikeBuildList = exports_.addResource('bike-build-list');
    bikeBuildList.addMethod('POST', exportDataIntegration, authMethodOptions);
    const familyContactList = exports_.addResource('family-contact-list');
    familyContactList.addMethod('POST', exportDataIntegration, authMethodOptions);

    // --- Reports ---
    const reports = apiRoot.addResource('reports');
    const savedReports = reports.addResource('saved');
    savedReports.addMethod('GET', manageReportsIntegration, authMethodOptions);
    savedReports.addMethod('POST', manageReportsIntegration, authMethodOptions);
    const savedReportById = savedReports.addResource('{id}');
    savedReportById.addMethod('DELETE', manageReportsIntegration, authMethodOptions);
    const reportsRun = reports.addResource('run');
    reportsRun.addMethod('POST', runReportIntegration, authMethodOptions);
    const reportsExport = reports.addResource('export');
    reportsExport.addMethod('POST', exportDataIntegration, authMethodOptions);

    // --- Cost Dashboard ---
    const costDashboard = apiRoot.addResource('cost-dashboard');
    costDashboard.addMethod('GET', getCostDataIntegration, authMethodOptions);
    const budget = costDashboard.addResource('budget');
    budget.addMethod('PUT', getCostDataIntegration, authMethodOptions);

    // --- Users ---
    const users = apiRoot.addResource('users');
    users.addMethod('GET', manageUsersIntegration, authMethodOptions);
    users.addMethod('POST', manageUsersIntegration, authMethodOptions);
    const userById = users.addResource('{id}');
    userById.addMethod('PUT', manageUsersIntegration, authMethodOptions);
    userById.addMethod('DELETE', manageUsersIntegration, authMethodOptions);
    const userDisable = userById.addResource('disable');
    userDisable.addMethod('POST', manageUsersIntegration, authMethodOptions);
    const userEnable = userById.addResource('enable');
    userEnable.addMethod('POST', manageUsersIntegration, authMethodOptions);

    // --- Audit Log ---
    const auditLog = apiRoot.addResource('audit-log');
    auditLog.addMethod('GET', getAuditLogIntegration, authMethodOptions);
    const auditLogExport = auditLog.addResource('export');
    auditLogExport.addMethod('POST', getAuditLogIntegration, authMethodOptions);

    // --- Giveaway Years ---
    const giveawayYears = apiRoot.addResource('giveaway-years');
    giveawayYears.addMethod('GET', manageGiveawayYearIntegration, authMethodOptions);
    const giveawayYearsActive = giveawayYears.addResource('active');
    giveawayYearsActive.addMethod('POST', manageGiveawayYearIntegration, authMethodOptions);
    const giveawayYearById = giveawayYears.addResource('{year}');
    const giveawayYearArchive = giveawayYearById.addResource('archive');
    giveawayYearArchive.addMethod('POST', manageGiveawayYearIntegration, authMethodOptions);
    const giveawayYearDelete = giveawayYearById.addResource('delete');
    giveawayYearDelete.addMethod('POST', manageGiveawayYearIntegration, authMethodOptions);

    // --- Auth ---
    const auth = apiRoot.addResource('auth');
    const authMe = auth.addResource('me');
    authMe.addMethod('GET', getAuthMeIntegration, authMethodOptions);

    // --- Config ---
    const config = apiRoot.addResource('config');
    const confidenceThreshold = config.addResource('confidence-threshold');
    confidenceThreshold.addMethod('GET', getCostDataIntegration, authMethodOptions);
    confidenceThreshold.addMethod('PUT', getCostDataIntegration, authMethodOptions);

    // ---------------------------------------------------------------
    // Rate Limiting — Usage Plan for public endpoints
    // ---------------------------------------------------------------

    const apiKey = this.api.addApiKey('BbpHkbgApiKey', {
      apiKeyName: 'bbp-hkbg-public-api-key',
      description: 'API key for rate-limiting public endpoints',
    });

    const usagePlan = this.api.addUsagePlan('PublicEndpointUsagePlan', {
      name: 'bbp-hkbg-public-usage-plan',
      description: 'Rate limiting for public endpoints (submit application, upload presign)',
      throttle: { rateLimit: 10, burstLimit: 20 },
      quota: { limit: 1000, period: apigateway.Period.DAY },
    });

    usagePlan.addApiKey(apiKey);
    usagePlan.addApiStage({
      stage: this.api.deploymentStage,
      throttle: [
        {
          method: applications.node.findChild('POST') as apigateway.Method,
          throttle: { rateLimit: 10, burstLimit: 20 },
        },
        {
          method: presign.node.findChild('POST') as apigateway.Method,
          throttle: { rateLimit: 10, burstLimit: 20 },
        },
      ],
    });

    // ---------------------------------------------------------------
    // Outputs
    // ---------------------------------------------------------------

    new cdk.CfnOutput(this, 'ApiUrl', {
      value: this.api.url,
      exportName: 'BbpHkbgApiUrl',
    });

    new cdk.CfnOutput(this, 'ApiId', {
      value: this.api.restApiId,
      exportName: 'BbpHkbgApiId',
    });
  }
}
