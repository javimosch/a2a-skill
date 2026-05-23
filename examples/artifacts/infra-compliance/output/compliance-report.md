# Infrastructure Compliance Report

**Generated:** 2026-05-23 16:29 UTC
**Scanner:** checkov
**Scope:** Terraform configuration compliance (CIS, HIPAA, GDPR, AWS best practices)

---

## Executive Summary

**Compliance Score: 0/100 — Grade F**

| Metric | Value |
|--------|-------|
| **Total Checks** | 29 |
| **Passed** | 8 |
| **Failed** | 21 |
| **Pass Rate** | 27.6% |
| **Critical** | 2 |
| **High** | 6 |
| **Medium** | 13 |
| **Low** | 0 |

### Severity Distribution

  🔴 **CRITICAL**: █ (2)
  🟠 **HIGH**: █████ (6)
  🟡 **MEDIUM**: ████████████ (13)

### 🔴 CRITICAL Severity Findings (2)

- **CKV_AWS_41**: Ensure no hard coded AWS access key and secret key exists in provider
  - Resource: `aws.default`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/secrets-policies/bc-aws-secrets-5](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/secrets-policies/bc-aws-secrets-5)
- **CKV_SECRET_2**: AWS Access Key
  - Resource: `25910f981e85ca04baf359199dd0bd4a3ae738b6`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/secrets-policies/secrets-policy-index/git-secrets-2](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/secrets-policies/secrets-policy-index/git-secrets-2)

### 🟠 HIGH Severity Findings (6)

- **CKV_AWS_130**: Ensure VPC subnets do not assign public IP by default
  - Resource: `aws_subnet.public`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/ensure-vpc-subnets-do-not-assign-public-ip-by-default](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/ensure-vpc-subnets-do-not-assign-public-ip-by-default)
- **CKV_AWS_24**: Ensure no security groups allow ingress from 0.0.0.0:0 to port 22
  - Resource: `aws_security_group.web`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/networking-1-port-security](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/networking-1-port-security)
- **CKV_AWS_382**: Ensure no security groups allow egress from 0.0.0.0:0 to port -1
  - Resource: `aws_security_group.web`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/bc-aws-382](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/bc-aws-382)
- **CKV_AWS_260**: Ensure no security groups allow ingress from 0.0.0.0:0 to port 80
  - Resource: `aws_security_group.web`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/ensure-aws-security-groups-do-not-allow-ingress-from-00000-to-port-80](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/ensure-aws-security-groups-do-not-allow-ingress-from-00000-to-port-80)
- **CKV2_AWS_6**: Ensure that S3 bucket has a Public Access block
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/s3-bucket-should-have-public-access-blocks-defaults-to-false-if-the-public-access-block-is-not-attached](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/s3-bucket-should-have-public-access-blocks-defaults-to-false-if-the-public-access-block-is-not-attached)
- **CKV_AWS_20**: S3 Bucket has an ACL defined which allows public READ access.
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/s3-policies/s3-1-acl-read-permissions-everyone](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/s3-policies/s3-1-acl-read-permissions-everyone)

### 🟡 MEDIUM Severity Findings (13)

- **CKV_AWS_23**: Ensure every security group and rule has a description
  - Resource: `aws_security_group.web`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/networking-31](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/networking-31)
- **CKV_AWS_273**: Ensure access is controlled through SSO and not AWS IAM defined users
  - Resource: `aws_iam_user.admin`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-iam-policies/bc-aws-273](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-iam-policies/bc-aws-273)
- **CKV_AWS_40**: Ensure IAM policies are attached only to groups or roles (Reducing access management complexity may in-turn reduce opportunity for a principal to inadvertently receive or retain excessive privileges.)
  - Resource: `aws_iam_user_policy_attachment.admin`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-iam-policies/iam-16-iam-policy-privileges-1](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-iam-policies/iam-16-iam-policy-privileges-1)
- **CKV_AWS_274**: Disallow IAM roles, users, and groups from using the AWS AdministratorAccess policy
  - Resource: `aws_iam_user_policy_attachment.admin`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-iam-policies/bc-aws-274](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-iam-policies/bc-aws-274)
- **CKV2_AWS_12**: Ensure the default security group of every VPC restricts all traffic
  - Resource: `aws_vpc.main`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/networking-4](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/networking-4)
- **CKV_AWS_18**: Ensure the S3 bucket has access logging enabled
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/s3-policies/s3-13-enable-logging](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/s3-policies/s3-13-enable-logging)
- **CKV_AWS_144**: Ensure that S3 bucket has cross-region replication enabled
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-general-policies/ensure-that-s3-bucket-has-cross-region-replication-enabled](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-general-policies/ensure-that-s3-bucket-has-cross-region-replication-enabled)
- **CKV2_AWS_62**: Ensure S3 buckets should have event notifications enabled
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-logging-policies/bc-aws-2-62](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-logging-policies/bc-aws-2-62)
- **CKV2_AWS_5**: Ensure that Security Groups are attached to another resource
  - Resource: `aws_security_group.web`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/ensure-that-security-groups-are-attached-to-ec2-instances-or-elastic-network-interfaces-enis](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-networking-policies/ensure-that-security-groups-are-attached-to-ec2-instances-or-elastic-network-interfaces-enis)
- **CKV_AWS_145**: Ensure that S3 buckets are encrypted with KMS by default
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-general-policies/ensure-that-s3-buckets-are-encrypted-with-kms-by-default](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-general-policies/ensure-that-s3-buckets-are-encrypted-with-kms-by-default)
- **CKV2_AWS_11**: Ensure VPC flow logging is enabled in all VPCs
  - Resource: `aws_vpc.main`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-logging-policies/logging-9-enable-vpc-flow-logging](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-logging-policies/logging-9-enable-vpc-flow-logging)
- **CKV2_AWS_61**: Ensure that an S3 bucket has a lifecycle configuration
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-logging-policies/bc-aws-2-61](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/aws-logging-policies/bc-aws-2-61)
- **CKV_AWS_21**: Ensure all data stored in the S3 bucket have versioning enabled
  - Resource: `aws_s3_bucket.data`
  - Guideline: [https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/s3-policies/s3-16-enable-versioning](https://docs.prismacloud.io/en/enterprise-edition/policy-reference/aws-policies/s3-policies/s3-16-enable-versioning)

---

## Remediation Recommendations

1. **Fix CKV_AWS_41** — Resource `aws.default`: Ensure no hard coded AWS access key and secret key exists in provider
2. **Fix CKV_SECRET_2** — Resource `25910f981e85ca04baf359199dd0bd4a3ae738b6`: AWS Access Key
3. **Ensure VPC subnets do not assign public IP by default** (Resource: `aws_subnet.public`, CKV_AWS_130) — Review and remediate per checkov guideline.
4. **Ensure no security groups allow ingress from 0.0.0.0:0 to port 22** (Resource: `aws_security_group.web`, CKV_AWS_24) — Review and remediate per checkov guideline.
5. **Ensure no security groups allow egress from 0.0.0.0:0 to port -1** (Resource: `aws_security_group.web`, CKV_AWS_382) — Review and remediate per checkov guideline.
6. **Ensure no security groups allow ingress from 0.0.0.0:0 to port 80** (Resource: `aws_security_group.web`, CKV_AWS_260) — Review and remediate per checkov guideline.
7. **Ensure that S3 bucket has a Public Access block** (Resource: `aws_s3_bucket.data`, CKV2_AWS_6) — Review and remediate per checkov guideline.
8. **S3 Bucket has an ACL defined which allows public READ access.** (Resource: `aws_s3_bucket.data`, CKV_AWS_20) — Review and remediate per checkov guideline.
9. **Ensure every security group and rule has a description** (Resource: `aws_security_group.web`, CKV_AWS_23) — Address as part of routine compliance maintenance.
10. **Ensure access is controlled through SSO and not AWS IAM defined users** (Resource: `aws_iam_user.admin`, CKV_AWS_273) — Address as part of routine compliance maintenance.
11. **Ensure IAM policies are attached only to groups or roles (Reducing access management complexity may in-turn reduce opportunity for a principal to inadvertently receive or retain excessive privileges.)** (Resource: `aws_iam_user_policy_attachment.admin`, CKV_AWS_40) — Address as part of routine compliance maintenance.
12. **Disallow IAM roles, users, and groups from using the AWS AdministratorAccess policy** (Resource: `aws_iam_user_policy_attachment.admin`, CKV_AWS_274) — Address as part of routine compliance maintenance.
13. **Ensure the default security group of every VPC restricts all traffic** (Resource: `aws_vpc.main`, CKV2_AWS_12) — Address as part of routine compliance maintenance.
14. **Ensure the S3 bucket has access logging enabled** (Resource: `aws_s3_bucket.data`, CKV_AWS_18) — Address as part of routine compliance maintenance.
15. **Ensure that S3 bucket has cross-region replication enabled** (Resource: `aws_s3_bucket.data`, CKV_AWS_144) — Address as part of routine compliance maintenance.
16. **Ensure S3 buckets should have event notifications enabled** (Resource: `aws_s3_bucket.data`, CKV2_AWS_62) — Address as part of routine compliance maintenance.
17. **Ensure that Security Groups are attached to another resource** (Resource: `aws_security_group.web`, CKV2_AWS_5) — Address as part of routine compliance maintenance.
18. **Ensure that S3 buckets are encrypted with KMS by default** (Resource: `aws_s3_bucket.data`, CKV_AWS_145) — Address as part of routine compliance maintenance.
19. **Ensure VPC flow logging is enabled in all VPCs** (Resource: `aws_vpc.main`, CKV2_AWS_11) — Address as part of routine compliance maintenance.
20. **Ensure that an S3 bucket has a lifecycle configuration** (Resource: `aws_s3_bucket.data`, CKV2_AWS_61) — Address as part of routine compliance maintenance.
21. **Ensure all data stored in the S3 bucket have versioning enabled** (Resource: `aws_s3_bucket.data`, CKV_AWS_21) — Address as part of routine compliance maintenance.
22. **Re-scan after fixes** — Run checkov after applying each remediation to verify the fix.
23. **Integrate into CI/CD** — Add `checkov -f main.tf` to your CI pipeline to prevent new compliance violations.

---

## Example Terraform Configuration (Scanned)

The following intentionally insecure Terraform configuration was scanned:

```hcl
# Intentionally insecure Terraform configuration for compliance scanning
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  # Hardcoded access key — security anti-pattern CKV_AWS_41
  access_key = "AKIAIOSFODNN7EXAMPLE"
  secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
  default     = "my-insecure-app-data-2026"
}

# VPC with public subnet
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "main-vpc"
    Environment = var.environment
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name = "public-subnet"
  }
}

# Overly permissive security group — CKV_AWS_24, CKV_AWS_260
resource "aws_security_group" "web" {
  name        = "web-sg"
  description = "Security group for web server"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from anywhere"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # CKV_AWS_260:0.0.0.0/0 on SSH
  }

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "web-sg"
  }
}

# S3 bucket without encryption or versioning — CKV_AWS_19, CKV_AWS_145
resource "aws_s3_bucket" "data" {
  bucket = var.bucket_name
  acl    = "public-read"  # CKV_AWS_20: S3 bucket ACL public-read

  tags = {
    Name        = var.bucket_name
    Environment = var.environment
  }
}

# Missing server-side encryption config — CKV_AWS_19
# Missing versioning config — CKV_AWS_145

# IAM user with full admin — CKV_AWS_40, CKV_AWS_63
resource "aws_iam_user" "admin" {
  name = "admin-user"
  path = "/system/"

  tags = {
    Environment = var.environment
  }
}

resource "aws_iam_user_policy_attachment" "admin" {
  user       = aws_iam_user.admin.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"  # CKV_AWS_63: full admin
}

# Access key without rotation — CKV_AWS_46
resource "aws_iam_access_key" "admin" {
  user = aws_iam_user.admin.name
}
```

---

*Report generated by a2a infra-compliance artifact using checkov.*