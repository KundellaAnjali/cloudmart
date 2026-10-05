# CloudMart

CloudMart is a serverless, cloud-native e-commerce application deployed on AWS. It provides product management, customer and order processing, inventory monitoring, token-based authentication and authorization, operational monitoring, alerts, a Flask dashboard, and automated business-report generation.

The project uses **Infrastructure as Code (IaC)** with AWS CloudFormation/AWS SAM and a **GitHub Actions CI/CD pipeline** using GitHub OIDC to obtain temporary AWS credentials.

---

## 1. What CloudMart Does

CloudMart provides:

- Product CRUD operations and inventory management.
- Customer creation and customer lookup.
- Order creation, retrieval and cancellation/status handling.
- Token-based API authentication through a Lambda Authorizer.
- Role-based authorization for `ADMIN`, `PRODUCT`, and `CUSTOMER` users.
- Event-driven order and inventory notifications using EventBridge and SNS.
- Custom CloudWatch metrics and alarms for business and infrastructure failures.
- A scheduled business-report Lambda that generates CSV reports and stores them in S3.
- A Flask monitoring/report dashboard hosted on an EC2 instance.
- Automated infrastructure deployment through GitHub Actions.



## 2. Architecture

### 2.1 High-level architecture

```mermaid
    DEV[Developer] --> GH[GitHub Repository]
    GH --> GA[GitHub Actions]
    GA --> OIDC[GitHub OIDC]
    OIDC --> STS[AWS STS]
    STS --> CFN[CloudFormation / AWS SAM]

    CLIENT[API Client] --> APIGW[API Gateway]
    APIGW --> AUTH[Lambda Authorizer]
    AUTH --> RDS[(RDS MySQL)]
    APIGW --> PRODUCT[Product Lambda]
    APIGW --> ORDER[Order Lambda]
    PRODUCT --> RDS
    ORDER --> RDS

    PRODUCT --> EB[EventBridge]
    ORDER --> EB
    EB --> SNS[SNS Notifications]

    SCHEDULE[EventBridge Schedule] --> REPORT[Report Lambda]
    REPORT --> RDS
    REPORT --> S3[(S3 Reports Bucket)]

    PRODUCT --> CW[CloudWatch]
    ORDER --> CW
    AUTH --> CW
    REPORT --> CW
    CW --> ALARMS[CloudWatch Alarms]
    ALARMS --> SNS

    EC2[EC2 Flask Dashboard] --> CW
    EC2 --> S3
    EC2 --> RDS
    EC2 --> SSM[SSM Parameter Store]
```

### 2.2 Network architecture

The current network template creates:

- VPC: `10.0.0.0/16`
- Public subnet: `10.0.1.0/24`
- Private subnet A: `10.0.2.0/24`
- Private subnet B: `10.0.3.0/24`
- Internet Gateway for the public subnet.
- Separate public and private route tables.
- EC2 dashboard in the public subnet.
- Lambda functions and RDS in private subnets.
- Security groups for EC2, Lambda and RDS.
- VPC endpoints for S3, SSM, SNS, EventBridge, CloudWatch Logs and CloudWatch Monitoring.

**Important:** the current `network-stack.yaml` does **not** create a NAT Gateway. Private resources reach supported AWS services through VPC endpoints. RDS is private and is not publicly accessible.


## 3. AWS Services Used


    Amazon VPC -> Network isolation, subnets, route tables and security groups 
    Internet Gateway -> Internet connectivity for the public subnet 
    VPC Endpoints -> Private access from the VPC to supported AWS services 
    AWS Lambda -> Product, order, authorization, schema initialization and reporting logic 
    Amazon API Gateway -> REST API entry point 
    Amazon RDS MySQL -> Primary relational database 
    Amazon S3 -> Business-report storage and SAM deployment artifacts 
    AWS SSM Parameter Store -> Database/configuration values 
    AWS KMS -> Encryption/decryption support for protected configuration 
    AWS IAM -> Service roles and least-privilege permissions 
    Amazon EventBridge -> Application events and scheduled report execution 
    Amazon SNS -> Customer/owner notifications and alarm notifications 
    Amazon CloudWatch -> Logs, custom metrics, AWS metrics, dashboards and alarms 
    Amazon EC2 -> Hosts the Flask dashboard 
    AWS CloudFormation -> Infrastructure as Code 
    AWS SAM -> Packaging/deployment of serverless stacks 
    GitHub Actions -> CI/CD automation 
    GitHub OIDC -> Short-lived AWS authentication for CI/CD 


## 4. Repository Structure

```text
cloudmart/
├── .github/
│   └── workflows/
│       ├── deploy.yaml
│
├── cloudformation/
│   ├── network-stack.yaml
│   ├── data-stack.yaml
│   ├── iam-stack.yaml
│   ├── auth-stack.yaml
│   ├── product-stack.yaml
│   ├── orders-stack.yaml
│   └── monitor-stack.yaml
│
├── dashboard/
│   ├── app.py
│   ├── requirements.txt
│   └── templates/
│       ├── dashboard.html
│       └── login.html
│
├── lambdas/
│   ├── authorizer/
│   │   ├── index.py
│   │   └── requirements.txt
│   ├── order/
│   │   ├── index.py
│   │   └── requirements.txt
│   ├── product/
│   │   ├── index.py
│   │   └── requirements.txt
│   ├── report/
│   │   ├── index.py
│   │   └── requirements.txt
│   └── schema-init/
│       ├── index.py
│       └── requirements.txt
│
├── layer/
│   └── python/
│       ├── pymysql/
│       ├── cryptography/
│       ├── cffi/
│       └── pycparser/
│
├── parameters/
│   └── parameters.json
│
├── Documents/
└── README.md
```
### Stack responsibilities

| Stack | Main responsibility |
|---|---|
| `cloudmart-network-stack` | VPC, subnets, route tables, security groups and VPC endpoints |
| `cloudmart-data-stack` | RDS MySQL, S3 reports bucket, KMS key and SSM parameters |
| `cloudmart-iam-stack` | Lambda and EC2 IAM roles |
| `cloudmart-auth-stack` | Schema initialization and Lambda Authorizer |
| `cloudmart-product-stack` | API Gateway, product Lambda and product routes; also defines the order Lambda/API routes |
| `cloudmart-orders-stack` | SNS topics/subscriptions and EventBridge notification rules |
| `cloudmart-monitor-stack` | Report Lambda, dashboard EC2 instance, CloudWatch dashboard and alarms |


## 5. Environment Configuration

The repository currently contains:

```json
[
  {
    "ParameterKey": "Environment",
    "ParameterValue": "dev"
  },
  {
    "ParameterKey": "AwsRegion",
    "ParameterValue": "ap-south-1"
  }
]
```

The deployment workflow reads the environment from `parameters/parameters.json` and exports it as `ENVIRONMENT`.

Supported template values are:

- `dev`
- `prod`

The current deployment workflow uses **AWS Region `ap-south-1`**.


## 6. Database Architecture

CloudMart uses a private MySQL RDS instance. The database is configured by the data stack with:

- Identifier: `${Environment}-cloudmart-db`
- Engine: MySQL
- Instance class: `db.t3.micro`
- Allocated storage: `20 GB`
- Database name: `cloudmart`
- `PubliclyAccessible: false`
- `MultiAZ: false`

The schema initialization Lambda creates the application tables.

### Main tables

```text
customers
    |
    | 1-to-many
    v
orders --------< order_items >-------- product
  |
  | 1-to-many
  v
order_status_history

```
The schema includes:

- `customers`
- `product`
- `orders`
- `order_items`
- `order_status_history`

The customer record contains authentication-related information including role. Order items retain product name and unit price at order time.


## 7. Configuration and Secrets

The application reads configuration from SSM Parameter Store using paths such as:

```text
/cloudmart/<environment>/db/host
/cloudmart/<environment>/db/name
/cloudmart/<environment>/db/username
/cloudmart/<environment>/db/password
/cloudmart/<environment>/inventory/stock-threshold
/cloudmart/<environment>/s3/reports-bucket
```

The database password is retrieved with decryption enabled.

The current data stack also creates a KMS key used by the IAM policies for decrypt operations.

**Do not put passwords, tokens, private keys or other secrets into GitHub.**

## 8. Authentication and Authorization

CloudMart uses an API Gateway TOKEN Lambda Authorizer.

```text
Client
  |
  | Authorization: <token>
  v
API Gateway
  |
  v
Lambda Authorizer
  |
  | Query customers table
  v
RDS MySQL
  |
  v
Validate token + active user + role
  |
  +---- ADMIN    -> broad API access
  +---- PRODUCT  -> product management access
  +---- CUSTOMER -> customer/order/product access

```
The authorizer:

1. Reads the token from the `Authorization` header.
2. Removes the optional `Bearer ` prefix.
3. Reads the user from the `customers` table.
4. Requires `is_active = TRUE`.
5. Publishes custom metrics for authorization outcomes and failures.
6. Places `role`, `customer_id` and `customer_name` in the authorizer context.
7. Returns an API Gateway IAM policy.

### Role behavior

**ADMIN**

The current authorizer generates a broad `Allow` policy.

**PRODUCT**

The current policy allows product GET/POST/PATCH/DELETE operations.

**CUSTOMER**

The current policy allows product reads, customer-specific access and order operations according to the authorizer policy.

The order Lambda also performs ownership checks using `requestContext.authorizer` values, so a non-admin customer cannot simply request another customer's data by changing a customer ID.


## 9. API Endpoints

The product stack creates a REST API with stage name equal to the environment.

Base URL format:

```text
https://<api-id>.execute-api.ap-south-1.amazonaws.com/<environment>
```

### Products

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/products` | List products | Public route in SAM |
| GET | `/products/{id}` | Get one product | Public route in SAM |
| POST | `/products` | Create product | Authorizer |
| PATCH | `/products/{id}` | Update product | Authorizer |
| DELETE | `/products/{id}` | Delete product | Authorizer |

### Customers

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/customers` | Create customer | Public route in SAM |
| GET | `/customers` | Retrieve customers | Authorizer |
| GET | `/customers/{id}` | Retrieve customer | Authorizer |

### Orders

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/orders` | Create order | Authorizer |
| GET | `/orders` | Retrieve orders | Authorizer |
| GET | `/orders/{id}` | Retrieve an order | Authorizer |
| PATCH | `/orders/{id}` | Cancel/update order status | Authorizer |



## 10. Lambda Functions

### Authorizer Lambda

File: `lambdas/authorizer/index.py`

Responsibilities:

- Validate API tokens against RDS.
- Determine the user's role.
- Return API Gateway allow/deny policies.
- Pass identity/role context to downstream Lambda functions.
- Publish custom authorization and failure metrics.

### Product Lambda

File: `lambdas/product/index.py`

Responsibilities include:

- Product creation.
- Product retrieval.
- Product update.
- Product deletion.
- Inventory quantity management.
- Database operations through PyMySQL.
- EventBridge publishing for relevant inventory events.
- Custom CloudWatch metrics.

### Order Lambda

File: `lambdas/order/index.py`

Responsibilities include:

- Customer creation and lookup.
- Order creation.
- Order retrieval.
- Customer-specific order filtering.
- Inventory updates associated with order processing.
- Order status/cancellation processing.
- Order status history.
- EventBridge event publishing.
- Custom CloudWatch metrics.

### Schema Initialization Lambda

File: `lambdas/schema-init/index.py`

Responsibilities:

- Connect to RDS.
- Create required tables if they do not exist.
- Initialize the application schema.
- Insert initial sample users during initialization.

The deployment workflow explicitly invokes:


```bash
aws lambda invoke \
  --function-name cloudmart-schema-init-${ENVIRONMENT} \
  response.json
```


### Report Lambda

File: `lambdas/report/index.py`

Responsibilities:

- Query active products.
- Query current-day orders using `DATE(order_date) = CURDATE()`.
- Calculate business metrics.
- Generate an in-memory CSV.
- Upload the CSV to the reports S3 bucket.
- Publish custom CloudWatch metrics.

Report files are stored using a key similar to:
```text
reports/cloudmart-business-report-YYYY-MM-DD-HH-MM-SS.csv
```
The report contains business summary information, product details and order details.


## 11. Event-Driven Processing

CloudMart uses EventBridge for application events.

### Order notifications

The order/product application publishes events to the default EventBridge event bus using source values such as:

```text
cloudmart.orders
cloudmart.inventory
```

The orders stack creates a customer notification rule for order events including:

- `OrderConfirmed`
- `OrderFailed`
- `OrderCancelled`

The matching events are sent to the customer SNS topic.

### Low-stock notification

The low-stock EventBridge rule listens for:
```text
source: cloudmart.inventory
detail-type: LowStock
```

and publishes the notification to the owner SNS topic.


## 12. Reporting

The monitor stack deploys the report Lambda using AWS SAM and configures a scheduled EventBridge trigger.

The report Lambda:

1. Reads database parameters from SSM.
2. Connects to RDS.
3. Reads active products.
4. Reads orders for the current database date.
5. Calculates totals and inventory statistics.
6. Creates CSV content in memory.
7. Writes the CSV to S3 under `reports/`.
8. Publishes success/failure metrics.

The report includes:

- Total Products
- Total Orders
- Confirmed Orders
- Cancelled Orders
- Total Revenue from confirmed orders
- Average Order Value
- Low Stock Products
- Highest Value Order
- Product details
- Order details


## 13. Monitoring and Alarms

CloudMart uses the custom CloudWatch namespace:
```text
CloudMart
```
Examples of custom metrics in the application include:

- `AuthorizedRequests`
- `UnauthorizedRequests`
- `ParameterAccessFailures`
- `RDSConnectionFailures`
- `DatabaseQueryFailures`
- `FailedOrders`
- `ReportGenerationFailures`
- `ReportLambdaFailures`
- `ReportUploadFailures`
- `S3AccessFailures`
- `ReportsGenerated`
- `LowStockProducts`
- `ReportUploadSuccess`

The monitor stack also creates alarms for Lambda errors/throttles, API Gateway 4XX/5XX errors, EC2 CPU, RDS CPU/connections, database connection failures, S3 access failures, report upload failures and parameter access failures.

### Important alarms

| Alarm | What it indicates |
|---|---|
| `CloudMart-FailedOrders-*` | Failed order metric crossed the configured threshold |
| `CloudMart-DatabaseQueryFailures-*` | Database query failures occurred |
| `CloudMart-UnauthorizedRequests-*` | Unauthorized requests were recorded |
| `CloudMart-ReportGenerationFailures-*` | Report generation failed |
| `CloudMart-LowStockProducts-*` | Low-stock condition was detected |
| `CloudMart-ApiGateway4XX-*` | API Gateway client errors |
| `CloudMart-ApiGateway5XX-*` | API Gateway/server errors |
| `CloudMart-RDSConnectionFailures-*` | Application could not connect to RDS |
| `CloudMart-S3AccessFailures-*` | Application encountered S3 access failure |
| `CloudMart-ParameterAccessFailures-*` | Application could not retrieve SSM parameters |

Alarm notifications are delivered through the SNS alarm topic configured by the monitor stack.


## 14. CloudMart Dashboard

The dashboard is a Flask application in `dashboard/app.py` and is hosted on an EC2 `t3.micro` instance.

The monitor stack provisions the instance in the **public subnet** and installs:

- Git
- Nginx
- Python 3
- pip
- MariaDB client

The EC2 user-data script clones the CloudMart repository, installs dashboard dependencies, creates a systemd service and configures Nginx as a reverse proxy.

```text
Browser
   |
   | HTTP :80
   v
Nginx
   |
   | proxy_pass
   v
Flask :5000
   |
   +--> CloudWatch
   +--> S3
   +--> RDS
   +--> SSM
   +--> EC2 metadata
```
The dashboard provides login, operational metrics, system-health information, report listing/viewing/download functionality and alarm status.

### Report download

The dashboard lists objects under:

```text
reports/
```

For downloads it generates a temporary S3 presigned URL rather than exposing the S3 bucket publicly.



## 15. CI/CD Pipeline

The primary workflow is:
```text
Push to main
     |
     v
GitHub Actions
     |
     +--> cfn-lint
     |
     v
GitHub OIDC
     |
     v
AWS IAM Role
     |
     v
Temporary STS credentials
     |
     v
Network
     |
     v
Data
     |
     v
IAM
     |
     v
Auth + Schema Init
     |
     v
Product
     |
     v
Orders
     |
     v
Monitor
```

The workflow uses:

```yaml
permissions:
  id-token: write
  contents: read
```
and configures AWS credentials through `aws-actions/configure-aws-credentials@v4` with the GitHub secret:

```text
ARN_ROLE
```

The AWS region configured by the workflow is:

```text
ap-south-1
```

### Main deployment sequence

1. Lint all templates.
2. Deploy network stack.
3. Deploy data stack.
4. Deploy IAM stack.
5. Validate/build/deploy auth stack with SAM.
6. Invoke schema initialization Lambda.
7. Validate/build/deploy product stack with SAM.
8. Validate/build/deploy orders stack with SAM.
9. Validate/build/deploy monitor stack with SAM.

## 16. Deployment Prerequisites

Before using the CI/CD pipeline, configure:

1. AWS account and access to the target region.
2. GitHub repository.
3. GitHub OIDC identity provider in AWS.
4. IAM deployment role trusted by GitHub OIDC.
5. GitHub repository secret `ARN_ROLE` containing the deployment role ARN.
6. `parameters/parameters.json` with the desired environment.
7. Required AWS permissions for the deployment role.
8. Verified SNS email subscriptions where notifications are required.

Do not commit credentials or authentication tokens.


## 17. Deployment

The recommended deployment path is GitHub Actions.
```bash
git add .
git commit -m "Deploy CloudMart changes"
git push origin main
```
The workflow then performs the stack deployments automatically.


## 18. Testing Checklist

### Authentication

- Missing token → protected endpoint should reject the request.
- Invalid token → request should be unauthorized.
- Valid active token → request reaches the permitted API route.
- Verify role is passed in the authorizer context.

### Products

- Create product as an authorized product-management role.
- Read products without authentication where the route is intentionally public.
- Read a product by ID.
- Update product.
- Delete product.
- Verify inventory/low-stock behavior.

### Orders

- Create an order with a valid customer context.
- Verify the order is stored in RDS.
- Verify inventory changes as implemented by the order logic.
- Retrieve orders.
- Retrieve an individual order.
- Verify customer ownership restrictions.
- Cancel an order and verify order history.

### Reports

- Invoke the report Lambda.
- Verify RDS connectivity.
- Verify CSV generation.
- Verify the object appears under `reports/` in S3.
- Verify the dashboard lists the report.
- Verify viewing/downloading the report.

### Monitoring

- Verify Lambda logs in CloudWatch.
- Verify custom `CloudMart` metrics.
- Trigger a controlled test failure where appropriate.
- Verify the corresponding alarm state.
- Verify SNS notification delivery.


## 19. Security Design

CloudMart uses several security controls:

- Private subnets for RDS and VPC-connected Lambda functions.
- RDS configured as not publicly accessible.
- Security groups controlling EC2/Lambda/RDS traffic.
- IAM roles for Lambda and EC2 service access.
- GitHub OIDC instead of long-lived AWS access keys in the CI/CD workflow.
- SSM Parameter Store for runtime configuration.
- KMS-based decryption permissions for protected configuration.
- Lambda Authorizer for token validation and role-based API authorization.
- S3 access through IAM rather than a public report bucket.
- Presigned URLs for dashboard report downloads.



## 20. Troubleshooting Quick Reference


| GitHub deployment fails | Check failed job, `cfn-lint`, AWS role/OIDC trust and CloudFormation events |
| `401 Unauthorized` | Check Authorization header, token, active customer record and authorizer logs |
| `403 Access denied` | Check user role and `customer_id` ownership checks |
| Lambda cannot reach RDS | Check RDS status, private subnets, Lambda/RDS security groups, SSM values and endpoints |
| Parameter access failure | Check SSM parameter path, IAM permission, KMS decrypt permission and endpoint connectivity |
| Report not generated | Check EventBridge schedule, report Lambda logs, RDS status, SSM and S3 permissions |
| Report generated but not visible | Check S3 `reports/` prefix and dashboard S3 permissions |
| Dashboard unavailable | Check EC2 status, security group port 80, Flask systemd service and Nginx status |
| Alarm is not firing | Check metric namespace/dimensions, threshold, period/evaluation periods and metric data |
| SNS notification missing | Check SNS subscription confirmation and alarm/rule target configuration |



## 21. Operational Notes

- The current deployment region is `ap-south-1`.
- The current environment parameter is `dev`.
- The RDS instance is private.
- The dashboard EC2 instance is public-subnet based and Nginx listens on port 80 while Flask listens on port 5000 locally.
- The private route table has no NAT route in the current template.
- VPC endpoints provide private connectivity to the AWS services explicitly configured in `network-stack.yaml`.
- SAM deployments use `--resolve-s3`, so SAM can create/use an S3 bucket for deployment artifacts.





