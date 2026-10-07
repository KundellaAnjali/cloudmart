# CloudMart — Deployment Prerequisites

Before deploying the CloudMart CloudFormation stacks, the following prerequisites must be completed.

## 1. AWS Account

An active AWS account is required for deploying and running the CloudMart infrastructure.

The project uses the AWS region:

```text
ap-south-1
```

---

## 2. CloudMart Code in GitHub

All required CloudMart source code and CloudFormation templates must be available in the GitHub repository.

The repository should contain:

```text
.github/workflows/
cloudformation/
dashboard/
lambdas/
layer/
parameters/
Documents/
README.md
```

The GitHub Actions workflow is used to deploy the CloudFormation stacks.

---

## 3. GitHub Actions OIDC Identity Provider

An **OpenID Connect (OIDC) Identity Provider** must be configured in AWS IAM for GitHub Actions.

The Identity Provider allows GitHub Actions to authenticate with AWS without storing long-term AWS access keys in GitHub.

---

## 4. IAM Deployment Role

An IAM role must be created for GitHub Actions.

The role must have a **trust policy** that allows GitHub Actions to assume the role through the configured OIDC Identity Provider.

The trust policy should restrict access to the required GitHub repository and branch according to the project's deployment configuration.

---

## 5. IAM Inline Policy

The GitHub Actions IAM deployment role must have an **inline policy** containing the permissions required to deploy the CloudMart CloudFormation stacks.

The policy should provide the required permissions for the AWS services and resources created or managed by the CloudFormation stacks, including services such as:

- CloudFormation
- IAM
- Lambda
- API Gateway
- EC2
- VPC
- RDS
- S3
- DynamoDB
- SSM Parameter Store
- KMS
- CloudWatch
- EventBridge
- SNS

The exact permissions should match the inline policy configured for the CloudMart deployment role.

---

## 6. IAM Role ARN in GitHub Secrets

After creating the IAM deployment role, obtain its ARN.

Example:

```text
arn:aws:iam::<account-id>:role/<CloudMart-GitHubActions-Role>
```

Store this IAM Role ARN in the **GitHub repository Secrets** using the secret name expected by the GitHub Actions workflow.

Example:

```text
AWS_ROLE_ARN
```

The GitHub Actions workflow uses this ARN to assume the AWS IAM deployment role through OIDC.

**Do not store AWS access keys in the repository.**

---

## 7. Database Password in SSM Parameter Store

Before deploying the CloudFormation stacks, the **RDS database password must be manually created in AWS Systems Manager Parameter Store**.

The password must be created using the **exact parameter path defined in the CloudFormation code**.

For the `dev` environment:

```text
/cloudmart/dev/db/password
```

Parameter type:

```text
SecureString
```

The actual database password should be entered manually as the parameter value.

### Important

The parameter path must exactly match the path referenced by the CloudFormation templates.

Do not:

- Put the database password in GitHub
- Put the password directly in the CloudFormation template
- Commit the password to the GitHub repository
- Store the actual password in `README.md`

The CloudFormation deployment retrieves the password from SSM Parameter Store when creating the RDS database.

---

## 8. Deployment Prerequisites Checklist

Before starting the CloudFormation deployment, verify:

- [ ] AWS account is available
- [ ] AWS region is configured as `ap-south-1`
- [ ] All CloudMart code is available in the GitHub repository
- [ ] GitHub Actions workflow is available
- [ ] AWS IAM OIDC Identity Provider for GitHub Actions is configured
- [ ] GitHub Actions IAM deployment role is created
- [ ] IAM role has the required trust policy
- [ ] IAM role has the required inline policy
- [ ] Inline policy has the required AWS service permissions
- [ ] IAM Role ARN is stored in GitHub Repository Secrets
- [ ] RDS database password is manually created in SSM Parameter Store
- [ ] SSM password parameter uses `SecureString`
- [ ] SSM parameter path exactly matches the path used in the CloudFormation code
