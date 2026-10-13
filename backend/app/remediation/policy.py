"""Validate execution configuration without creating an AWS SDK session."""
import re

ROLE_ARN = re.compile(r'arn:(aws|aws-us-gov|aws-cn):iam::([0-9]{12}):role/[A-Za-z0-9+=,.@_/-]+')


def execution_role_error(connection):
    role = connection.get('execution_role_arn', '')
    if not role:
        return 'Configure a separate AWS execution role before enabling live execution.'
    match = ROLE_ARN.fullmatch(role)
    if not match or match.group(2) != connection.get('account_id'):
        return 'The execution role must be a valid IAM role ARN in the configured AWS account.'
    if role == connection.get('role_arn'):
        return 'Monitoring and execution must use different IAM roles.'
    return None
