terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "monitor" {
  name = "cloud-optimizer-monitor"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = var.trusted_principal_arn }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "sts:ExternalId" = var.external_id } }
    }]
  })
}

resource "aws_iam_role_policy" "monitor" {
  role = aws_iam_role.monitor.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ec2:DescribeInstances", "rds:DescribeDBInstances", "rds:ListTagsForResource",
        "cloudwatch:GetMetricStatistics", "ce:GetCostAndUsage", "pricing:GetProducts"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role" "executor" {
  name               = "cloud-optimizer-executor"
  assume_role_policy = aws_iam_role.monitor.assume_role_policy
}

resource "aws_iam_role_policy" "executor" {
  role = aws_iam_role.executor.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ec2:DescribeInstances"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:StopInstances"]
        Resource = "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"
        Condition = {
          StringEquals = {
            "ec2:ResourceTag/optimizer:managed" = "true"
            "ec2:ResourceTag/Environment"       = "demo"
          }
        }
      }
    ]
  })
}

resource "aws_security_group" "demo" {
  count       = var.create_demo_instance ? 1 : 0
  name_prefix = "optimizer-demo-"
  description = "No inbound access for optimizer demo"
  vpc_id      = var.vpc_id
}

resource "aws_instance" "demo" {
  count                       = var.create_demo_instance ? 1 : 0
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.demo[0].id]
  associate_public_ip_address = false
  metadata_options {
    http_tokens = "required"
  }
  root_block_device {
    encrypted = true
  }
  tags = {
    Name                = "optimizer-demo"
    Environment         = "demo"
    "optimizer:managed" = "true"
  }
}

output "monitor_role_arn" {
  value = aws_iam_role.monitor.arn
}
output "executor_role_arn" {
  value = aws_iam_role.executor.arn
}
